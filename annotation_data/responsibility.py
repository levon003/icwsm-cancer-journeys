from collections import Counter
from tqdm import tqdm
import itertools
import pandas as pd
import numpy as np

from db import get_annotation_db
from journal import get_journal_text, get_journal_info, get_journal_text_representation

responsibility_labels = ["communicating", "info_filtering", "clinical_decisions", "preparation", "symptom_management",
                         "coordinating_support", "sharing_medical_info", "compliance",
                         "managing_transitions", "financial_management", "continued_monitoring", "giving_back",
                         "behavior_changes"]
responsibility_codes = ["CO", "IF", "CD", "PR", "ST", "CS", "SM", "CP", "MT", "FM", "CM", "GB", "BC"]
responsibility_label_to_code_map = {resp_label: responsibility_codes[i] for i, resp_label in enumerate(responsibility_labels)}
responsibility_labels_with_support_management = responsibility_labels + ["support_management"]
responsibility_labels_with_none = responsibility_labels + ["none"]
responsibility_labels_with_all = responsibility_labels + ["none", "support_management"]

"""
This is the set of responsibility labels with Cohen's kappa > 0.4
"""
high_irr_responsibility_labels = ["coordinating_support", "sharing_medical_info", "compliance", "financial_management", "giving_back", "behavior_changes"]
high_irr_responsibility_codes = [responsibility_codes[responsibility_labels.index(resp_label)] for resp_label in high_irr_responsibility_labels]


def sort_responsibility_list(responsibility_list):
    return sorted(responsibility_list, key=lambda responsibility: responsibility_labels_with_all.index(responsibility))


def get_labels_from_responsibility_string(responsibility_string, include_none=False,
                                          warn_on_legacy_responsibilities=True):
    """

    :param responsibility_string:
    :param include_none: If 'none' should be included in the returned list when no other responsibilities are present
    :return:
    """
    if responsibility_string == "":
        return ['none'] if include_none else []
    labels = responsibility_string.split('|')
    if len(labels) == 0:
        print("WARNING: No responsibilities identified, including none")
        if include_none:
            labels = ['none']
    if not include_none and "none" in labels:
        labels.remove("none")
    # For legacy reasons, we handle support_management, but we replace it with the newer version of the codebook
    if "support_management" in labels:
        labels.remove("support_management")
        labels.append("sharing_medical_info")
        labels.append("coordinating_support")
        if warn_on_legacy_responsibilities:
            print("WARNING: Replaced support management with its newer codes.")
    # we sort the responsibility list to ensure they will always appear in a standard order
    # will throw an exception if an invalid responsibility occurred in the string
    labels = sort_responsibility_list(labels)
    return labels


def get_responsibility_annotations(conflict_resolution_strategy="or"):
    try:
        db = get_annotation_db()
        # the most recent version of the annotation guidance was set at this date,
        # so we restrict to since this time period
        created_at = '2018-08-23'
        cursor = db.execute("""
            SELECT a.site_id, a.journal_oid, a.data, a.username, c.correct_username 
            FROM journalAnnotation a LEFT JOIN journalAnnotationConflictResolution c 
            ON a.site_id = c.site_id AND a.journal_oid = c.journal_oid AND a.annotation_type = c.annotation_type 
            WHERE a.annotation_type = "journal_patient_responsibilities" AND a.data <> ""
            AND a.created >= ?
            GROUP BY a.site_id, a.journal_oid, a.username 
            ORDER BY a.id DESC
        """, (created_at,))

        responsibility_annotations = []

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
            responsibilities = None
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
                        print(
                            f"WARNING: {correct_username} not found in {annotator_usernames}. Replacing with 'unknown'.")
                        data = 'unknown'
                else:  # no correction for this journal
                    responsibilities, conflict_status = \
                        resolve_responsibility_annotation_conflicts(rows,
                                                                    resolution_strategy=conflict_resolution_strategy)
            if data is None and responsibilities is None:
                raise ValueError("Unexpected and unhandled conflicts between a journal's responsibility annotations.")
            if responsibilities is None:
                responsibilities = get_labels_from_responsibility_string(data)
            responsibility_annotation_data = {'site_id': site_id,
                                              'journal_oid': journal_oid,
                                              'conflict_status': conflict_status,
                                              'responsibilities': responsibilities}
            responsibility_annotations.append(responsibility_annotation_data)
        return responsibility_annotations
    finally:
        db.close()

        
def get_responsibility_annotations_dataframe():
    df = get_responsibility_annotations_by_username_dataframe()

    responsibility_annotations = []

    # group by the journals, writing a single line for each journal in the dataset
    for key, group in df.groupby(by=['site_id', 'journal_oid']):
        rows = group
        site_id, journal_oid = key
        # We are considering all of the annotations for a single journal here

        responsibilities = None
        if len(rows) == 1:
            row = rows.iloc[0]
            assert row['correct_username'] is None or row['correct_username'] == ""
            annotator_usernames = row['username']
            conflict_status = "SINGLE USER"
            responsibilities = row.responsibilities
        else:  # 2 or more annotators
            first_row = rows.iloc[0]
            if first_row['correct_username'] is not None and first_row['correct_username'] != "":
                # this annotation was corrected!
                correct_username = first_row['correct_username']
                conflict_status = "RESOLVED"
                selected_row = rows[rows.username == correct_username]

                if len(selected_row) == 0:
                    # this condition implies an invalid correction in the database
                    print(
                        f"WARNING: {correct_username} not found in {annotator_usernames}. Replacing with 'unknown'.")
                    responsibilities = ['unknown']
                elif len(selected_row) > 1:
                    raise ValueError("Multiple annotations from same username.")
                else:
                    responsibilities = selected_row.iloc[0].responsibilities
            else:  # no correction for this journal
                # use the or strategy
                conflict_status = 'CONFLICT'
                responsibility_sets = rows.apply(lambda row: set(row.responsibilities), axis=1)
                included_responsibilities = set()
                for responsibility_set in responsibility_sets:
                    included_responsibilities = included_responsibilities | responsibility_set
                if len(included_responsibilities) == 0:
                    responsibilities = ['unknown']
                else:
                    responsibilities = sort_responsibility_list(list(included_responsibilities))
        if responsibilities is None:
            raise ValueError("Unexpected and unhandled conflicts between a journal's responsibility annotations.")
        responsibility_annotation_data = {'site_id': site_id,
                                          'journal_oid': journal_oid,
                                          'conflict_status': conflict_status,
                                          'responsibilities': responsibilities}
        responsibility_annotations.append(responsibility_annotation_data)
    return pd.DataFrame(responsibility_annotations)


def get_responsibility_annotations_by_username():
    try:
        db = get_annotation_db()
        created_at = '2018-08-23'
        cursor = db.execute("""
                    SELECT a.site_id, a.journal_oid, a.data, a.username, c.correct_username 
                    FROM journalAnnotation a LEFT JOIN journalAnnotationConflictResolution c 
                    ON a.site_id = c.site_id AND a.journal_oid = c.journal_oid AND a.annotation_type = c.annotation_type 
                    WHERE a.annotation_type = "journal_patient_responsibilities" AND a.data <> ""
                    AND a.created >= ?
                    GROUP BY a.site_id, a.journal_oid, a.username 
                    ORDER BY a.id DESC
                """, (created_at,))

        responsibility_annotations = []
        rows = cursor.fetchall()
        for row in rows:
            site_id, journal_oid = row['site_id'], row['journal_oid']
            username = row['username']
            is_corrected = row['correct_username'] is not None and row['correct_username'] != ""
            responsibilities = get_labels_from_responsibility_string(row['data'])
            responsibility_annotation_data = {'site_id': site_id,
                                              'journal_oid': journal_oid,
                                              'username': username,
                                              'responsibilities': responsibilities,
                                              'is_corrected': is_corrected}
            responsibility_annotations.append(responsibility_annotation_data)
        return responsibility_annotations
    finally:
        db.close()
        
        
def get_responsibility_annotations_by_username_dataframe():
    """Fixed version of get_responsibility_annotations_by_username() which should be preferred."""
    try:
        db = get_annotation_db()
        created_at = '2018-08-23'
        cursor = db.execute("""
                    SELECT a.site_id, a.journal_oid, a.data, a.username, a.id, c.correct_username
                    FROM journalAnnotation a LEFT JOIN journalAnnotationConflictResolution c 
                    ON a.site_id = c.site_id AND a.journal_oid = c.journal_oid AND a.annotation_type = c.annotation_type 
                    WHERE a.annotation_type = "journal_patient_responsibilities" AND a.data <> ""
                    AND a.created >= ?
                    GROUP BY a.site_id, a.journal_oid, a.username, a.id
                    ORDER BY a.id DESC
                """, (created_at,))

        responsibility_annotations = []
        rows = cursor.fetchall()
        for row in rows:
            site_id, journal_oid = row['site_id'], row['journal_oid']
            username = row['username']
            correct_username = row['correct_username']
            responsibilities = get_labels_from_responsibility_string(row['data'])
            responsibility_annotation_data = {'site_id': site_id,
                                              'journal_oid': journal_oid,
                                              'username': username,
                                              'correct_username': correct_username,
                                              'responsibilities': responsibilities,
                                              'id': row['id']}
            responsibility_annotations.append(responsibility_annotation_data)
        
        responsibility_df = pd.DataFrame(responsibility_annotations)
        new_df_inds = [group.id.idxmax() 
                       for key, group 
                       in responsibility_df.groupby(by=['site_id', 'journal_oid', 'username'])]
        new_df = responsibility_df.loc[new_df_inds].copy()
        new_df.reset_index(inplace=True)
        
        return new_df
    finally:
        db.close()


def resolve_responsibility_annotation_conflicts(rows, allow_majority_agreement=True, resolution_strategy="or"):
    """

    :param rows: Rows of annotations containing 'data'
    :param allow_majority_agreement: If annotation sets with at least one set of complete agreement ought to be
    allowed as a no-conflict situation
    :param resolution_strategy: View the source for the exact implementation of each approach.
    Valid values are: 'none', 'empty', 'min2', 'and', 'or' (default)
    :return: The responsibilities, as resolved from any conflict,
    and a string describing the status of conflict resolution
    """
    combinations = [(combo[0]['data'] == combo[1]['data'], combo[0]['data'])
                    for combo in itertools.combinations(rows, 2)]
    agreements = [data for is_match, data in combinations if is_match is True]

    responsibilities = None  # this function resolves conflicts, assigning this list of responsibilities

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
        if resolution_strategy == "none":
            data = ""
            responsibilities = ['none']
        elif resolution_strategy == "empty":
            data = ""
            responsibilities = []
        elif resolution_strategy == "min2":
            # this strategy includes all annotations used at least twice between annotators
            data = ""
            responsibility_lists = [get_labels_from_responsibility_string(row['data']) for row in rows]
            rep_counter = Counter(list(itertools.chain(*responsibility_lists)))
            responsibilities = []
            for responsibility, count in rep_counter.most_common():
                if count < 2:  # only include responsibilities that occur at least twice
                    break
                responsibilities.append(responsibility)
        elif resolution_strategy == "and":
            # includes all responsibilities selected by all annotators
            responsibility_sets = [set(get_labels_from_responsibility_string(row['data'])) for row in rows]
            responsibilities = sort_responsibility_list(list(set.intersection(*responsibility_sets)))
        elif resolution_strategy == "or" or resolution_strategy == "all_checked":
            # includes all responsibilities present among the annotations
            responsibility_sets = [set(get_labels_from_responsibility_string(row['data'])) for row in rows]
            responsibilities = sort_responsibility_list(list(set.union(*responsibility_sets)))
        else:
            raise ValueError(f"Resolution strategy f{resolution_strategy} unknown.")
    if responsibilities is None:
        responsibilities = get_labels_from_responsibility_string(data)
    return responsibilities, conflict_status


def get_annotated_responsibility_df(conflict_score_cost=0.1):
    """

    :return: Pandas DataFrame with the following columns:
        site_id, journal_oid, is_annotated, conflict_status, responsibilities, {responsibility_name}_score, journal_text

    """
    responsibility_annotations = get_responsibility_annotations()
    df_entries = []
    for ra in tqdm(responsibility_annotations):
        site_id, journal_oid = ra['site_id'], ra['journal_oid']
        responsibilities = ra['responsibilities']
        journal_text = get_journal_text(site_id, journal_oid)
        if journal_text is None:
            continue
        conflict_status = ra['conflict_status']
        new_entry = {'site_id': site_id,
                     'journal_oid': journal_oid,
                     'is_annotated': True,
                     'conflict_status': ra['conflict_status'],
                     'responsibilities': responsibilities,
                     'journal_text': journal_text}
        for resp_label in responsibility_labels:
            score = int(resp_label in responsibilities)
            if conflict_status == "CONFLICT" and score == 1:
                score -= conflict_score_cost
            new_entry[resp_label + "_score"] = score
        df_entries.append(new_entry)
    df = pd.DataFrame(df_entries)
    return df


def get_annotated_responsibility_df_fixed(conflict_score_cost=0.1, resp_subset=responsibility_labels):
    """

    :return: Pandas DataFrame with the following columns:
        site_id, journal_oid, is_annotated, conflict_status, responsibilities, {responsibility_name}_score, journal_text

    """
    df = get_responsibility_annotations_dataframe()
    df['journal_text'] = df.apply(lambda row: get_journal_text(row.site_id, row.journal_oid), axis=1)
    df.drop(df[df.journal_text.isna()].index, inplace=True)
    assert np.sum(df.journal_text.isna()) == 0
    df['is_annotated'] = True
    for resp_label in resp_subset:
        df[resp_label + "_score"] = df.apply(lambda row: int(resp_label in row.responsibilities) - conflict_score_cost if row.conflict_status == "CONFLICT" else int(resp_label in row.responsibilities), axis=1)
    df.reset_index(inplace=True)
    return df


def add_journals_to_responsibility_df(df, new_entries):
    """
    Add the given [unannotated] journals to the given df.

    :param df: A df generated by get_annotated_responsibility_df()
    :param new_entries: A list of dictionaries containing the keys 'site_id' and 'journal_oid'
    :return: The new dataframe containing both.
    """
    df_entries = []
    for e in tqdm(new_entries):
        site_id, journal_oid = e['site_id'], e['journal_oid']
        journal_text = get_journal_text(site_id, journal_oid)
        if journal_text is None:
            continue
        new_entry = {'site_id': site_id,
                     'journal_oid': journal_oid,
                     'is_annotated': False,
                     'conflict_status': None,
                     'responsibilities': [],
                     'journal_text': journal_text}
        df_entries.append(new_entry)
    unannotated_df = pd.DataFrame(df_entries)
    new_df = pd.concat([df, unannotated_df], ignore_index=True)
    new_df.drop_duplicates(subset=['site_id', 'journal_oid'], keep='first', inplace=True)
    return new_df


def add_sites_to_responsibility_df(df, new_entries, drop_duplicate_journals=True):
    """
    Add the given [unannotated] sites to the given df.

    :param df: A df generated by get_annotated_responsibility_df()
    :param new_entries: A list of integer site_ids
    :return: The new dataframe containing all journals in the sites indicated by new_entries
    """
    df_entries = []
    for site_id in tqdm(new_entries):
        journals = get_journal_info(site_id)
        for journal in journals:
            journal_text = get_journal_text_representation(journal)
            if journal_text is None:
                continue
            new_entry = {'site_id': site_id,
                         'journal_oid': journal['journal_oid'],
                         'is_annotated': False,
                         'conflict_status': None,
                         'responsibilities': [],
                         'journal_text': journal_text}
            df_entries.append(new_entry)
    unannotated_df = pd.DataFrame(df_entries)
    new_df = pd.concat([df, unannotated_df], ignore_index=True)
    if drop_duplicate_journals:
        new_df.drop_duplicates(subset=['site_id', 'journal_oid'], keep='first', inplace=True)
    return new_df
