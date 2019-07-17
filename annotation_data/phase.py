
from tqdm import tqdm
import pandas as pd
import numpy as np
from collections import Counter
import itertools

from db import get_annotation_db
from utils import *
from journal import *

phase_labels = ['pretreatment', 'treatment', 'end_of_life', 'cured']
phase_labels_with_unknown = phase_labels + ['unknown']
valid_transitions=[('pretreatment', 'treatment'),
                   ('treatment', 'end_of_life'),
                   ('treatment', 'cured'),
                   ('cured', 'treatment')]
# in addition, self-loops are always allowed
valid_transitions.extend([(phase, phase) for phase in phase_labels])

DEFAULT_TREATMENT_SITE_IDS = [714287, 623581]


def sort_phase_list(phase_list):
    return sorted(phase_list, key=lambda phase: phase_labels_with_unknown.index(phase))


def get_labels_from_phase_string(phase, remove_unknown=False):
    """

    :param phase: The phase string, as stored in the annotation database.
    (Assumes that phases are defined as particular strings and that they are separated by '|'.)
    :param remove_unknown: If the 'unknown' label should be removed from the returned list
    :return: A list of the phase labels extracted from the given phase string
    """
    if phase == "":
        return []
    labels = phase.split('|')
    if remove_unknown and 'unknown' in labels:
        labels.remove('unknown')
    if 'screening' in labels or 'info_seeking' in labels:
        if 'screening' in labels:
            labels.remove('screening')
        if 'info_seeking' in labels:
            labels.remove('info_seeking')
        labels.insert(0, 'pretreatment')
    # we sort the phase list to ensure they will always appear in a standard order
    # will throw an exception if an invalid phase occurred in the string
    labels = sort_phase_list(labels)
    # a given journal should never have more than 2 phases tagged + unknown
    if len(labels) > 3:
        raise ValueError(f"Phase string tags an impossible {len(labels)} phases simultaneously.")
    return labels


def combine_phase_annotations(annotation1, annotation2):
    """
    Note: This function ASSUMES that annotation1 != annotation2
    """
    phases1 = get_labels_from_phase_string(annotation1)
    phases2 = get_labels_from_phase_string(annotation2)
    combo = set(phases1) | set(phases2)
    if 'unknown' in combo:
        combo.remove('unknown')
    transition_validity_list = [(phase1, phase2) in valid_transitions or (phase2, phase1) in valid_transitions
                                for phase1, phase2 in itertools.combinations(combo, 2)]
    if False in transition_validity_list:
        # This created an illegal combination!
        return ['unknown']
    combo.add('unknown')  # we always add unknown in this case, since there was disagreement between the two annotations
    return sort_phase_list(list(combo))


def get_phase_annotations(conflict_resolution_strategy="combine"):
    try:
        db = get_annotation_db()
        cursor = db.execute("""
            SELECT a.site_id, a.journal_oid, a.data, a.username, c.correct_username 
            FROM journalAnnotation a LEFT JOIN journalAnnotationConflictResolution c 
            ON a.site_id = c.site_id AND a.journal_oid = c.journal_oid AND a.annotation_type = c.annotation_type 
            WHERE a.annotation_type = "journal_journey_phase" AND a.data <> ""
            GROUP BY a.site_id, a.journal_oid, a.username 
            ORDER BY a.id DESC
        """)

        phase_annotations = []
        ambiguous_phase_annotation_count = 0

        # Sort the returned annotations so that we can group by the individual journals
        def group_by_journal_function(row):
            return row['site_id'], row['journal_oid']

        # group by the journals, writing a single line for each journal in the dataset
        all_rows = cursor.fetchall()
        all_rows.sort(key=group_by_journal_function)
        for key, group in itertools.groupby(all_rows, group_by_journal_function):
            rows = list(group)
            site_id, journal_oid = key
            # We are considering all of the annotations for a single journal here

            data = None
            phases = None
            if len(rows) == 1:
                assert rows[0]['correct_username'] is None or rows[0]['correct_username'] == ""
                annotator_usernames = rows[0]['username']
                conflict_status = "SINGLE USER"
                data = rows[0]['data']
            else:  # 2 or more annotators
                # get the list of annotator names
                annotator_usernames = "|".join(sorted([row['username'] for row in rows]))
                if rows[0]['correct_username'] is not None and rows[0]['correct_username'] != "":
                    # this annotation was corrected!
                    correct_username = rows[0]['correct_username']
                    conflict_status = "RESOLVED"
                    data = None
                    for row in rows:
                        if row['username'] == correct_username:
                            data = row['data']
                            if data is None:
                                raise ValueError("Annotation unexpectedly lacks data.")
                    if data is None:
                        # this condition implies an invalid correction in the database
                        print(f"WARNING: {correct_username} not found in {annotator_usernames}. Replacing with 'unknown'.")
                        data = 'unknown'
                else:  # no correction for this journal
                    phases, conflict_status = \
                        resolve_phase_annotation_conflicts(rows, resolution_strategy=conflict_resolution_strategy)
            if data is None and phases is None:
                raise ValueError("Unexpected and unhandled conflicts between a journal's phase annotations.")
            if phases is None:
                phases = get_labels_from_phase_string(data)
            phase_annotation_data = {'site_id': site_id,
                                     'journal_oid': journal_oid,
                                     'conflict_status': conflict_status,
                                     'phases': phases}
            phase_annotations.append(phase_annotation_data)

        return phase_annotations
    finally:
        db.close()


def resolve_phase_annotation_conflicts(rows, allow_majority_agreement=True, resolution_strategy="combine"):
    """

    :param rows: Rows of annotations containing 'data'
    :param allow_majority_agreement: If annotation sets with at least one set of complete agreement ought to be
    allowed as a no-conflict situation
    :param resolution_strategy: View the source for the exact implementation of each approach.
    Valid values are: 'unknown', 'none', 'and', 'or', 'safe_or', 'combine' (default)
    :return: The phases, as resolved from any conflict, and a string describing the status of conflict resolution
    """
    combinations = [(combo[0]['data'] == combo[1]['data'], combo[0]['data'])
                    for combo in itertools.combinations(rows, 2)]
    agreements = [data for is_match, data in combinations if is_match is True]

    phases = None  # this function resolves conflicts, assigning this phase list

    if len(agreements) == len(combinations):  # all annotators agree
        conflict_status = "NO CONFLICT"
        data = agreements[0]
    elif allow_majority_agreement and len(agreements) >= 1:  # at least one pair of annotators agree
        # note that this isn't the same as majority agreement if > 3 annotators have annotated a single journal
        # but at the time of implementation that will never happen
        conflict_status = "MINIMAL CONFLICT"
        data = agreements[0]
    else:  # no agreements between any of the annotators!
        # this annotation was not corrected and there is no absolute agreement
        # In this situation, we'll resolve based on the resolution strategy
        conflict_status = "CONFLICT"
        if resolution_strategy == "unknown":
            data = 'unknown'
            phases = ['unknown']
        elif resolution_strategy == "none":
            data = ""
            phases = []
        elif resolution_strategy == "and":
            # includes all phases selected by all annotators
            phase_sets = [set(get_labels_from_phase_string(row['data'])) for row in rows]
            phases = sort_phase_list(list(set.intersection(*phase_sets)))
        elif resolution_strategy == "or" or resolution_strategy == "all_checked":
            # includes all phases present among the annotations
            # this strategy may be dangerous to use because
            phase_sets = [set(get_labels_from_phase_string(row['data'])) for row in rows]
            phases = sort_phase_list(list(set.union(*phase_sets)))
        elif resolution_strategy == "safe_or":
            # includes all phases present among the annotations
            # but, if an illegal phase combination is created, will reset to 'unknown'
            phase_sets = [set(get_labels_from_phase_string(row['data'])) for row in rows]
            phases = sort_phase_list(list(set.union(*phase_sets)))
            if 'unknown' in phases:
                phases.remove('unknown')
            transition_validity_list = [(phase1, phase2) in valid_transitions or (phase2, phase1) in valid_transitions
                                        for phase1, phase2 in itertools.combinations(phases, 2)]
            if False in transition_validity_list:
                # This created an illegal combination of annotations!
                phases = ['unknown']
        elif resolution_strategy == "combine":
            # In this situation, we'll try to combine the annotations if there are two annotators,
            # otherwise just returning 'unknown'
            data = "unknown"
            if len(rows) > 2:
                print("WARNING: 3+ annotators, but no agreement. Setting 'unknown'.",
                      [r['username'] for r in rows])
                phases = ['unknown']
            else:
                phases = combine_phase_annotations(rows[0]['data'], rows[1]['data'])
        else:
            raise ValueError(f"Resolution strategy f{resolution_strategy} unknown.")
    if phases is None:
        phases = get_labels_from_phase_string(data)
    return phases, conflict_status


def get_phase_annotations_by_username():
    try:
        db = get_annotation_db()
        cursor = db.execute("""
            SELECT a.site_id, a.journal_oid, a.data, a.username, c.correct_username 
            FROM journalAnnotation a LEFT JOIN journalAnnotationConflictResolution c 
            ON a.site_id = c.site_id AND a.journal_oid = c.journal_oid AND a.annotation_type = c.annotation_type 
            WHERE a.annotation_type = "journal_journey_phase" AND a.data <> ""
            GROUP BY a.site_id, a.journal_oid, a.username 
            ORDER BY a.id DESC
        """)

        phase_annotations = []
        rows = cursor.fetchall()
        for row in rows:
            site_id, journal_oid = row['site_id'], row['journal_oid']
            username = row['username']
            is_corrected = row['correct_username'] is not None and row['correct_username'] != ""
            phases = get_labels_from_phase_string(row['data'])
            phase_annotation_data = {'site_id': site_id,
                                     'journal_oid': journal_oid,
                                     'username': username,
                                     'phases': phases,
                                     'is_corrected': is_corrected}
            phase_annotations.append(phase_annotation_data)
        return phase_annotations
    finally:
        db.close()


def trim_phase_annotations_by_valid_sites(phase_annotations, valid_sites, print_report=True):
    """

    :param phase_annotations: Iterable that can be keyed on 'site_id'
    :param valid_sites: List of site_ids from which to exclude annotations
    :param print_report: If a report about the excluded sites should be printed to stdout
    :return:
    """
    site_ids_not_in_candidate_sites = []
    phase_annotations_filtered = []
    for a in phase_annotations:
        site_id = a['site_id']
        if site_id not in valid_sites:
            site_ids_not_in_candidate_sites.append(site_id)
        else:
            phase_annotations_filtered.append(a)
    if print_report:
        excluded_site_counts = Counter(site_ids_not_in_candidate_sites).most_common()
        for site_id, count in excluded_site_counts:
            print('Not valid site excluded:', count, site_id, get_webclient_url(site_id))
    return phase_annotations_filtered


def group_by_site_id(phase_annotations):
    """
    This is the function that groups by site_id and actually retrieves the journal data.

    This function does 3 things:
    1) Retrieves text data for all journals on a site with annotations
    2) Filters out annotations for sites that aren't completely or near-completely annotated
    3) Returns a dataframe of the annotations with phases and text together

    """
    site_id_count, total_journal_count = 0, 0

    annotated_journal_list = []  # a list of dictionaries, so that it can be turned into a Pandas dataframe

    def sort_by_site_id(tup):
        return tup['site_id']

    phase_annotations = sorted(phase_annotations, key=sort_by_site_id)
    for k, g in tqdm(itertools.groupby(phase_annotations, sort_by_site_id)):
        site_id = k
        site_annotations = list(g)
        if len(site_annotations) < 5:
            continue  # only want complete sites, and sites with less than five definitely aren't complete

        journals = get_journal_info(site_id)
        assert len(site_annotations) <= len(journals)

        journals = [j for j in journals if j['text_length'] >= 50]
        unannotated_journals = len(journals) - len(site_annotations)
        if unannotated_journals > 1:
            print("\nSite %d lacks %d journals with phase annotations; %s" % (
            site_id, unannotated_journals, get_webclient_url(site_id)))
            print("It will be excluded unless the whole site is coded for phases!")
            continue  # not every non-trivial journal on this site is coded

        annotations_added = 0
        unmatched_count = 0
        annotation_dict = {a['journal_oid']: a['phases'] for a in site_annotations}
        for journal in journals:
            if journal['journal_oid'] not in annotation_dict:
                unmatched_count += 1
                continue
            journal_phases = annotation_dict[journal['journal_oid']]

            journal['phases'] = "|".join(journal_phases)

            journal_text = get_journal_text_representation(journal)
            # FIXME Make this more robust
            if len(annotated_journal_list) > 0:
                prev_journal_text = annotated_journal_list[-1]['journal_text']
            else:
                prev_journal_text = ""
            if len(annotated_journal_list) > 1:
                prev_prev_journal_text = annotated_journal_list[-2]['journal_text']
            else:
                prev_prev_journal_text = ""

            journal['journal_text'] = journal_text
            # journal['text'] = prev_prev_journal_text + " " + FLD + " 2 " + prev_journal_text + " " + FLD + " 3 " + journal_text

            annotated_journal_list.append(journal)
            annotations_added += 1

        total_journal_count += annotations_added
        site_id_count += 1

    columns = ['site_id', 'journal_oid', 'journal_index', 'text', 'phases']
    df = pd.DataFrame(annotated_journal_list, columns=columns)
    print("Sites:", site_id_count, "; total annotated journals:", total_journal_count, "; df len:", len(df))
    return df


def get_annotated_phase_df(conflict_score_cost=0.1, unknown_score_cost=0.2):
    """

    :return: Pandas DataFrame with the following columns:
        site_id, journal_oid, journal_index, is_annotated, conflict_status, phases, {phase_name}_score, journal_text

    """
    phase_annotations = get_phase_annotations()
    df_entries = []

    def sort_by_site_id(tup):
        return tup['site_id']

    phase_annotations = sorted(phase_annotations, key=sort_by_site_id)
    for k, g in tqdm(itertools.groupby(phase_annotations, sort_by_site_id)):
        site_id = k
        site_annotations = list(g)
        if len(site_annotations) < 5:
            continue  # only want complete sites, and sites with less than five definitely aren't complete

        journals = get_journal_info(site_id)
        assert len(site_annotations) <= len(journals)

        annotation_dict = {a['journal_oid']: a for a in site_annotations}
        
        journals = [j for j in journals if j['text_length'] >= 50]
        unannotated_journals = len(journals) - len(site_annotations)
        if unannotated_journals > 1:
            if site_id in DEFAULT_TREATMENT_SITE_IDS:
                # This is an exception created originally for two sites coded by Saumik
                # The sites had too many journals, so to save time the unannotated journals should just be treatment
                # We construction new annotations and inject them into the annotation_dict
                for journal in journals:
                    if journal['journal_oid'] not in annotation_dict:
                        new_annotation = {'phases': ['treatment'], 'conflict_status': 'NO CONFLICT'}
                        annotation_dict[journal['journal_oid']] = new_annotation
            else:
                print("\nSite %d lacks %d journals with phase annotations; %s" % (
                    site_id, unannotated_journals, get_webclient_url(site_id)))
                print("It will be excluded unless the whole site is coded for phases!")
                continue  # not every non-trivial journal on this site is coded

        unmatched_count = 0
        journal_index = 0
        for journal in journals:

            site_id, journal_oid = journal['site_id'], journal['journal_oid']
            journal_text = get_journal_text_representation(journal)
            if journal_text is None:
                continue
            if journal_oid not in annotation_dict:
                unmatched_count += 1
                continue

            annotation = annotation_dict[journal_oid]
            journal_phases = annotation['phases']
            conflict_status = annotation['conflict_status']

            new_entry = {'site_id': site_id,
                         'journal_oid': journal_oid,
                         'journal_index': journal_index,
                         'created_at': journal['created_at'],
                         'is_annotated': True,
                         'conflict_status': conflict_status,
                         'phases': journal_phases,
                         'journal_text': journal_text}
            journal_index += 1

            unknown_score_penalty = unknown_score_cost if 'unknown' in phase_labels else 0
            for phase_label in phase_labels:
                score = int(phase_label in journal_phases)
                if score >= 0.5:
                    score -= unknown_score_penalty
                    if conflict_status == "CONFLICT":
                        score -= conflict_score_cost
                new_entry[phase_label + "_score"] = score

            df_entries.append(new_entry)

        if unmatched_count > 0:
            print(f"{unmatched_count} non-trivial journals did not have annotations on site {site_id} and were skipped.")

    columns = ['site_id', 'journal_oid', 'journal_index', 'created_at',
               'is_annotated', 'conflict_status', 'phases', 'journal_text']
    columns += [phase_label + "_score" for phase_label in phase_labels]
    df = pd.DataFrame(df_entries, columns=columns)
    return df


def add_sites_to_phase_df(df, new_entries, disallow_duplicate_sites=True):
    """
    Add the given [unannotated] sites to the given df.

    :param df: A df generated by get_annotated_phase_df()
    :param new_entries: A list of integer site_ids
    :param disallow_duplicate_sites: If true, journals will only be added from sites not already in the df.
    :return: The new dataframe containing all journals in the sites indicated by new_entries
    """
    existing_site_ids = set(df.site_id)
    skipped_sites_count = 0
    df_entries = []
    for site_id in tqdm(new_entries):
        if disallow_duplicate_sites and site_id in existing_site_ids:
            skipped_sites_count += 1
            continue
        journals = get_journal_info(site_id)
        journal_index = 0
        for journal in journals:
            journal_text = get_journal_text_representation(journal)
            if journal_text is None:
                continue
            new_entry = {'site_id': site_id,
                         'journal_oid': journal['journal_oid'],
                         'journal_index': journal_index,
                         'created_at': journal['created_at'],
                         'is_annotated': False,
                         'conflict_status': None,
                         'phases': [],
                         'journal_text': journal_text}
            journal_index += 1
            df_entries.append(new_entry)
    unannotated_df = pd.DataFrame(df_entries)
    new_df = pd.concat([df, unannotated_df], ignore_index=True)
    if skipped_sites_count > 0:
        print(f"Skipped {skipped_sites_count} sites that were found already in the dataframe.")
    return new_df


def add_time_since_prev_journal_column(df, default_value=-1.0):
    df['seconds_since_previous_journal'] = np.full(len(df), default_value)
    for site_id, group in tqdm(df.groupby(by='site_id', sort=False)):
        if len(group) == 1:
            print(f"Site {site_id} only has a single valid journal, which may indicate an issue: {get_webclient_url(site_id)}")
            continue
        prev = None
        for curr in group.index:
            if prev is None:
                prev = curr
                continue
            time_diff = group.at[curr, 'created_at'] - group.at[prev, 'created_at']
            df.at[curr, 'seconds_since_previous_journal'] = int(time_diff / 1000)
            prev = curr
        #for i in range(1, len(group)):
        #    curr_row = group.iloc[i]
        #    prev_row = group.iloc[i-1]
        #    assert prev_row.journal_index + 1 == curr_row.journal_index
        #    time_diff = curr_row.created_at - prev_row.created_at
        #    curr_row.seconds_since_previous_journal = int(time_diff / 1000)

        
def get_initial_label(phases):
    if len(phases) == 0:
        return None
    phase = phases[0]
    labels = get_labels_from_phase_string(phase, remove_unknown=True)
    if len(labels) == 0:
        return get_initial_label(phases[1:])
    elif len(labels) == 1:
        return labels[0]
    elif len(labels) > 1:
        return seek_phase_forward(labels, phases, 1)
    
    
def get_final_label(phases):
    if len(phases) == 0:
        return None
    phase = phases[-1]
    labels = get_labels_from_phase_string(phase, remove_unknown=True)
    if len(labels) == 0:
        return get_initial_label(phases[:-1])
    elif len(labels) == 1:
        return labels[0]
    elif len(labels) > 1:
        return seek_phase_backward(labels, phases, -2)

    
def get_transitions(phases):
    transitions = []
    prev_labels = None
    for i in range(len(phases)):
        phase = phases[i]
        curr_labels = get_labels_from_phase_string(phase, remove_unknown=True)
        if len(curr_labels) == 0:
            continue
        elif prev_labels is None:
            prev_labels = curr_labels
            continue
        elif prev_labels == curr_labels:
            if len(curr_labels) > 1:  # this is the nightmare scenario...
                # What SHOULD happen here is we base the entire chain of transitions here as 
                # being the NEXT transition that happens... unless this appears at the end of the phase string,
                # at which point it's based on the PREVIOUS transition that happens
                print("Warning: Ambiguous transition.")
            transition = (prev_labels[0], curr_labels[0])
            transitions.append(transition)
        else:
            # There is a difference! A transition must have occurred
            transition = (prev_labels[-1], curr_labels[0])
            if len(prev_labels) == 2 and len(curr_labels) == 1:
                curr_label = curr_labels[0]
                if curr_label in prev_labels:
                    prev_labels.remove(curr_label)
                    transition = (prev_labels[0], curr_label)
                else:
                    print("Warning: Two labels to 1 different label; assuming latest phase.")
                    prev_label = prev_labels[-1]
                    if prev_label == 'cured':
                        print("  This is the specifically bad case where 'cured' is linked to something other than treatment!")
                    transition = (prev_label, curr_label)
            elif len(prev_labels) == 1 and len(curr_labels) == 2:
                prev_label = prev_labels[0]
                if prev_label in curr_labels:
                    curr_labels_copy = curr_labels[:]
                    curr_labels_copy.remove(prev_label)
                    curr_label = curr_labels_copy[0]
                    transition = (prev_label, curr_label)
                else:
                    print("Warning: 1 label to 2 different labels. Assuming earliest phase.")
                    curr_label = curr_labels[0]
                    transition = (prev_label, curr_label)
            elif len(prev_labels) == 2 and len(curr_labels) == 2:
                print("Warning: 2 labels to 2 different labels. I hope this never happens!")
                print("  Assuming transition:", transition, prev_labels, curr_labels)
            transitions.append(transition)
        prev_labels = curr_labels
    return transitions
    
    
def seek_phase_forward(prev_labels, phases, index):
    if index >= len(phases):
        print("Warning: Reached end of list while attempting to resolve ambiguous phase transition.")
        return prev_labels[0]
    curr_phase = phases[index]
    curr_labels = get_labels_from_phase_string(curr_phase, remove_unknown=True)
    
    if set(prev_labels) == set(curr_labels):
        # no new information, keep seeking
        return seek_phase_forward(curr_labels, phases, index + 1)
    elif len(curr_labels) == 0:  # no information from this journal
        return seek_phase_forward(prev_labels, phases, index + 1)
    elif len(curr_labels) == 1:  # we found a single-label journal
        curr_label = curr_labels[0]
        if curr_label in prev_labels:
            # return the OTHER label
            prev_labels.remove(curr_label)
            target_label = prev_labels[-1]
        else:
            print("Warning: Ambiguous transition from 2 phases to 1 phase.")
            target_label = prev_labels[-1]  # in this situation, assume it was the latest of the phases
        return target_label
    elif len(curr_labels) >= 2:
        print("Warning: This should never happen. (2-label journal followed by a journal with a different two labels.)")
        return None
    
    
def seek_phase_backward(prev_labels, phases, index):
    if index * -1 > len(phases):
        print("Warning: Reached start of list while attempting to resolve ambiguous phase transition.")
        return prev_labels[-1]
    curr_phase = phases[index]
    curr_labels = get_labels_from_phase_string(curr_phase, remove_unknown=True)
    
    if set(prev_labels) == set(curr_labels):
        # no new information, keep seeking
        return seek_phase_backward(curr_labels, phases, index - 1)
    elif len(curr_labels) == 0:  # no information from this journal
        return seek_phase_backward(prev_labels, phases, index - 1)
    elif len(curr_labels) == 1:  # we found a single-label journal
        curr_label = curr_labels[0]
        if curr_label in prev_labels:
            # return the OTHER label
            prev_labels.remove(curr_label)
            target_label = prev_labels[-1]
        else:
            print("Warning: Ambiguous transition from 2 phases to 1 phase.")
            target_label = prev_labels[0]  # in this situation, assume it was the first of the phases
            # basically, this is like (pre) -> (treatment|eol); we assume and return (treatment) here as the final phase
        return target_label
    elif len(curr_labels) >= 2:
        print("Warning: This should never happen. (2-label journal preceded by a journal with a different two labels.)")
        return None