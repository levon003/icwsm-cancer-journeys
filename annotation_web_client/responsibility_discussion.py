from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, make_response
)
from werkzeug.exceptions import abort

from annotation_web_client.auth import login_required
from annotation_web_client.db import get_db
from annotation_web_client.annotate import get_journal_annotations, get_journal_annotation
from annotation_web_client.site_df import get_site_df, get_journals, get_journals_user_dict
from annotation_web_client.sites import generate_site
from annotation_web_client.journal_db import get_journal_db
from annotation_web_client.prediction import get_journal_prediction

import pandas as pd
import random

bp = Blueprint('responsibility_discussion', __name__)

IS_ANNOTATION_CHANGED_EVIDENCE_DESCRIPTION = "You indicated that this post does not contain the responsibility.\n"

@bp.route('/discussion/journal/summary/generate_batch', methods=('POST',))
def handle_generate_batch():
    if request.method != 'POST':
        raise ValueError("Unexpected request type to generation endpoint.")

    phase = request.form['phase']
    current_username = request.form['current_username']
    other_username = request.form['other_username']
    responsibility = request.form['responsibility']

    if phase == "evidence":
        evidence_username = current_username
        reconsider_username = other_username
        if not generate_evidence_batch(responsibility, evidence_username, reconsider_username):
            return make_response("Evidence batch generation failed.", 400)
    elif phase == "reconsider":
        evidence_username = other_username
        reconsider_username = current_username
        if not generate_reconsider_batch(responsibility, evidence_username, reconsider_username):
            return make_response("Reconsider batch generation failed.", 400)
    else:
        return make_response(f"Invalid phase '{phase}'.", 400)

    return make_response("OK", 200)


@bp.route(
    '/discussion/journal/summary/<current_user>/<other_user>/responsibility/<responsibility>',
    methods=('GET', 'POST'))
def view_journal_discussion_summary(current_user, other_user, responsibility):
    evidence_tasks = get_existing_tasks(responsibility, current_user, other_user, "evidence")
    reconsider_tasks = get_existing_tasks(responsibility, current_user, other_user, "reconsider")

    if evidence_tasks is None:
        incomplete_evidence_tasks = []
        complete_evidence_tasks = []
    else:
        incomplete_evidence_tasks = evidence_tasks[~evidence_tasks["is_complete"]].to_dict('records')
        complete_evidence_tasks = evidence_tasks[evidence_tasks["is_complete"]].to_dict('records')
    if reconsider_tasks is None:
        incomplete_reconsider_tasks = []
        complete_reconsider_tasks = []
    else:
        incomplete_reconsider_tasks = reconsider_tasks[~reconsider_tasks["is_complete"]].to_dict('records')
        complete_reconsider_tasks = reconsider_tasks[reconsider_tasks["is_complete"]].to_dict('records')

    return render_template('discussion/journalResponsibilityDiscussionSummary.html',
                           responsibility=responsibility,
                           current_user=current_user,
                           other_user=other_user,
                           incomplete_evidence_tasks=incomplete_evidence_tasks,
                           incomplete_reconsider_tasks=incomplete_reconsider_tasks,
                           complete_evidence_tasks=complete_evidence_tasks,
                           complete_reconsider_tasks=complete_reconsider_tasks)


@bp.route(
    '/discussion/journal/<phase>/<evidence_user>/<reconsider_user>/responsibility/<responsibility>/<int:discussion_id>',
    methods=('GET', 'POST'))
def view_journal_discussion(phase, evidence_user, reconsider_user, responsibility, discussion_id):
    if request.method == 'POST':
        return handle_journal_discussion_post(phase, evidence_user, reconsider_user, responsibility, discussion_id)

    if phase not in ["evidence", "reconsider"]:
        return make_response("Unknown discussion phase.", 400)

    task = get_discussion_task(responsibility, phase, discussion_id, evidence_user, reconsider_user)
    entry = get_discussion_entry(responsibility, phase, discussion_id, evidence_user, reconsider_user, task['batch_id'])

    if entry is not None:
        highlighted_text, additional_discussion, is_annotation_changed = entry['highlighted_text'], entry['additional_discussion'], entry['is_annotation_changed']
        highlighted_text = "" if highlighted_text is None else highlighted_text
        additional_discussion = "" if additional_discussion is None else additional_discussion
        is_annotation_changed_desc = "yes" if is_annotation_changed else "no"
        if phase == "evidence" and is_annotation_changed == 1:
            if not additional_discussion.startswith(IS_ANNOTATION_CHANGED_EVIDENCE_DESCRIPTION):
                additional_discussion = IS_ANNOTATION_CHANGED_EVIDENCE_DESCRIPTION + additional_discussion
    else:
        is_annotation_changed_desc = "not set"
        highlighted_text = ""
        additional_discussion = ""

    target_journal_oid = task['journal_oid']
    site_id = task['site_id']
    site = generate_site(site_id)

    target_journal = None
    for journal in site["journals"]:
        if journal["journal_oid"] == target_journal_oid:
            target_journal = journal
            break
    if target_journal is None:
        return make_response("Couldn't find requested journal.", 500)

    highlighted_text_evidence = ""
    additional_discussion_evidence = ""
    if phase == "reconsider":
        # during the reconsider phase, need to retrieve the entry from the Evidence phase that corresponds
        # in order to populate the evidence under consideration
        evidence_entry = identify_discussion_entry(responsibility, "evidence", evidence_user, reconsider_user,
                                                   site_id, target_journal_oid)
        if evidence_entry is None:
            return make_response("Couldn't find the evidence corresponding to this Reconsider task in the database.", 500)
        if evidence_entry['is_annotation_changed'] == 1:
            print(f"Warning: Unexpected link from Reconsider task to an Evidence task that DID change its annotation... Evidence entry DB ID: {evidence_entry['id']}")
        highlighted_text_evidence = evidence_entry['highlighted_text']
        additional_discussion_evidence = evidence_entry['additional_discussion']

    if phase == "evidence":
        template = "discussion/journalResponsibilityDiscussionEvidence.html"
    elif phase == "reconsider":
        template = "discussion/journalResponsibilityDiscussionReconsider.html"
    return render_template(template,
                           phase=phase,
                           batch_id=task['batch_id'],
                           discussion_id=discussion_id,
                           next_discussion_id=task['next_discussion_id'],
                           discussion_phase=phase,
                           responsibility=responsibility,
                           site=site,
                           journal=target_journal,
                           evidence_user=evidence_user,
                           reconsider_user=reconsider_user,
                           show_annotation_tools=False,
                           highlighted_text=highlighted_text,
                           additional_discussion=additional_discussion,
                           is_annotation_changed=is_annotation_changed_desc,
                           highlighted_text_evidence=highlighted_text_evidence,
                           additional_discussion_evidence=additional_discussion_evidence)


def handle_journal_discussion_post(phase, evidence_user, reconsider_user, responsibility, discussion_id):
    # save the value from the request

    batch_id = int(request.form['batch_id'])
    site_id = int(request.form['site_id'])
    journal_oid = request.form['journal_oid']

    highlighted_text = request.form['highlighted_text']
    additional_discussion = request.form['additional_discussion']
    is_annotation_changed = request.form['is_annotation_changed'] == "true"
    is_annotation_changed = 1 if is_annotation_changed else 0

    if phase == "evidence" \
            and is_annotation_changed == 0 \
            and additional_discussion.strip().startswith(IS_ANNOTATION_CHANGED_EVIDENCE_DESCRIPTION.strip()):
        print("WARNING: Annotator indicated Evidence task shouldn't change annotation, but they had previously indicated that they WOULD change the annotation.")

    db = get_db()
    db.execute(
        """INSERT INTO discussionEntry
        (site_id, journal_oid, responsibility, phase, batch_id, discussion_id, evidence_username, reconsider_username, highlighted_text, additional_discussion, is_annotation_changed) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (site_id, journal_oid, responsibility, phase, batch_id, discussion_id, evidence_user, reconsider_user, highlighted_text, additional_discussion, is_annotation_changed)
    )
    db.commit()

    return make_response("OK", 200)


def get_discussion_task(responsibility, phase, discussion_id, evidence_user, reconsider_user):
    db = get_db()
    cursor = db.execute(
        """SELECT * FROM discussionTask 
        WHERE responsibility = ? AND phase = ? AND discussion_id = ? AND evidence_username = ? AND reconsider_username = ? AND batch_id = (SELECT MAX(batch_id) FROM discussionTask 
                WHERE responsibility = ? AND evidence_username = ? AND reconsider_username = ? AND phase = ?)
                ORDER BY id DESC""",
        (responsibility, phase, discussion_id, evidence_user, reconsider_user, responsibility, evidence_user, reconsider_user, phase)
    )
    results = cursor.fetchall()
    # assert len(results) == 1  # unknown if this is a required condition...
    return results[0]


def get_discussion_entry(responsibility, phase, discussion_id, evidence_user, reconsider_user, batch_id):
    db = get_db()
    cursor = db.execute(
        """SELECT * FROM discussionEntry
        WHERE responsibility = ? AND phase = ? AND discussion_id = ? AND evidence_username = ? AND reconsider_username = ? AND batch_id = ?
                ORDER BY id DESC""",
        (responsibility, phase, discussion_id, evidence_user, reconsider_user, batch_id)
    )
    results = cursor.fetchall()
    if results is None or len(results) == 0:
        return None
    return results[0]


def identify_discussion_entry(responsibility, phase, evidence_user, reconsider_user, site_id, journal_oid):
    db = get_db()
    cursor = db.execute(
        """SELECT * FROM discussionEntry
        WHERE responsibility = ? AND phase = ? AND evidence_username = ? AND reconsider_username = ? 
        AND site_id = ? AND journal_oid = ?
                ORDER BY id DESC""",
        (responsibility, phase, evidence_user, reconsider_user, site_id, journal_oid)
    )
    results = cursor.fetchall()
    if results is None or len(results) == 0:
        return None
    return results[0]



def get_discussion_entries(responsibility, phase, evidence_user, reconsider_user):
    db = get_db()
    cursor = db.execute(
        """SELECT * FROM discussionEntry
        WHERE responsibility = ? AND phase = ? AND evidence_username = ? AND reconsider_username = ?
        GROUP BY site_id, journal_oid
        ORDER BY id DESC""",
        (responsibility, phase, evidence_user, reconsider_user)
    )
    results = cursor.fetchall()
    if results is None or len(results) == 0:
        return []
    return results


def generate_evidence_batch(responsibility, evidence_username, reconsider_username, batch_size=20):
    responsibility_annotations = get_responsibility_annotations_by_username()
    resp_df = pd.DataFrame(responsibility_annotations)
    resp_df = resp_df[resp_df['is_corrected'] == False]

    disagreement_list = []
    journals_evaluated = 0
    for key, group in resp_df.groupby(by=("site_id", "journal_oid")):
        if len(group) <= 1:
            continue
        annotating_users = set(group['username'])
        if evidence_username not in annotating_users or reconsider_username not in annotating_users:
            continue
        journals_evaluated += 1

        evidence_user_responsibilities = group[group['username'] == evidence_username].iloc[0]['responsibilities']
        reconsider_user_responsibilities = group[group['username'] == reconsider_username].iloc[0]['responsibilities']

        evidence_user_present = responsibility in evidence_user_responsibilities
        reconsider_user_present = responsibility in reconsider_user_responsibilities
        if evidence_user_present and not reconsider_user_present:
            site_id, journal_oid = key
            disagreement = {
                "site_id": int(site_id),
                "journal_oid": journal_oid,
                "evidence_username": evidence_username,
                "reconsider_username": reconsider_username,
            }
            disagreement_list.append(disagreement)

    print(f"Explored {journals_evaluated} journals for Evidence disagreements, finding {len(disagreement_list)} relevant disagreements.")
    if len(disagreement_list) == 0:
        # No failure generating the list, but there weren't any disagreements to include
        return True

    disagreement_list = remove_completed_disagreement_tasks(
        disagreement_list, evidence_username, reconsider_username, responsibility)
    if len(disagreement_list) == 0:
        # No failure generating the list, but there weren't any disagreements to include
        return True
    random.shuffle(disagreement_list)
    new_batch = disagreement_list[:batch_size]

    # Create a new batch in the database
    db = get_db()

    cursor = db.execute("""SELECT MAX(batch_id) AS max_batch_id FROM discussionTask 
                WHERE responsibility = ? AND evidence_username = ? AND reconsider_username = ? AND phase = 'evidence'
                """, (responsibility, evidence_username, reconsider_username))
    result = cursor.fetchone()
    prev_batch_id = result['max_batch_id']
    if prev_batch_id is None:
        batch_id = 0
    else:
        batch_id = prev_batch_id + 1

    for discussion_id, disagreement in enumerate(new_batch):
        next_discussion_id = discussion_id + 1
        if next_discussion_id == len(new_batch):
            next_discussion_id = 0
        db.execute(
            """INSERT INTO discussionTask 
            (site_id, journal_oid, responsibility, phase, batch_id, discussion_id, next_discussion_id, evidence_username, reconsider_username) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (disagreement['site_id'], disagreement['journal_oid'], responsibility, "evidence", batch_id, discussion_id, next_discussion_id, evidence_username, reconsider_username)
        )

    db.commit()

    print(f"Created new batch of {len(new_batch)} Evidence tasks with batch_id {batch_id}.")

    return True


def remove_completed_disagreement_tasks(disagreement_list, evidence_username, reconsider_username, responsibility):
    # retrieve DisagreementTasks by site_id, journal_oid, evidence_username, reconsider_username, responsibility
    discussion_entries = get_discussion_entries(responsibility, "evidence", evidence_username, reconsider_username)
    existing_entries = {(entry['site_id'], entry['journal_oid'])
                        for entry in discussion_entries
                        if is_evidence_discussion_entry_filled(entry)}
    if len(existing_entries) == 0:
        print("No completed Evidence discussion tasks, so no candidate disagreements were trimmed.")
        return disagreement_list

    # look for site_id/journal_oid overlaps and remove
    all_candidate_journals = {(dis['site_id'], dis['journal_oid']) for dis in disagreement_list}
    remaining_candidates = all_candidate_journals - existing_entries
    print(f"Removed {len(all_candidate_journals) - len(remaining_candidates)} journals that already have completed Evidence discussion tasks, leaving {len(remaining_candidates)} from which to generate a new batch.")
    print(f"{len(existing_entries)} Evidence tasks were considered for overlap.")

    # create new disagreement list from the remaining candidates
    new_disagreement_list = [{
                "site_id": candidate[0],
                "journal_oid": candidate[1],
                "evidence_username": evidence_username,
                "reconsider_username": reconsider_username,
            } for candidate in remaining_candidates]
    return new_disagreement_list


def is_evidence_discussion_entry_filled(discussion_entry):
    return discussion_entry['is_annotation_changed'] == 1 \
           or discussion_entry['highlighted_text'] != "" \
           or discussion_entry['additional_discussion'] != ""


def is_reconsider_discussion_entry_filled(discussion_entry):
    # Currently, we consider all Reconsider discussion entries to be filled, as long as they indicate if the annotation
    # should be changed or not
    return discussion_entry['is_annotation_changed'] is not None


def generate_reconsider_batch(responsibility, evidence_username, reconsider_username, batch_size=20):
    discussion_entries = get_discussion_entries(responsibility, "evidence", evidence_username, reconsider_username)

    print(f"Prior to removal of unfilled and annotation-changing journals, identified {len(discussion_entries)} Evidence task entries.")
    discussion_candidates = [{"site_id": entry['site_id'],
                              "journal_oid": entry['journal_oid'],
                              "batch_id": entry['batch_id'],
                              "discussion_id": entry['discussion_id']}
                             for entry in discussion_entries
                             if is_evidence_discussion_entry_filled(entry) and entry['is_annotation_changed'] == 0]
    # TODO Need to trim Evidence entries with existing Reconsider entries
    print(f"Explored completed Evidence tasks, finding {len(discussion_candidates)} relevant disagreements.")

    if len(discussion_candidates) == 0:
        print("After trimming, no candidate journals were identified for Reconsider tasks.")
        return True

    random.shuffle(discussion_candidates)
    new_batch = discussion_candidates[:batch_size]

    # Create a new batch in the database
    db = get_db()

    cursor = db.execute("""SELECT MAX(batch_id) AS max_batch_id FROM discussionTask 
                    WHERE responsibility = ? AND evidence_username = ? AND reconsider_username = ? AND phase = 'reconsider'
                    """, (responsibility, evidence_username, reconsider_username))
    result = cursor.fetchone()
    prev_batch_id = result['max_batch_id']
    if prev_batch_id is None:
        batch_id = 0
    else:
        batch_id = prev_batch_id + 1

    for discussion_id, disagreement in enumerate(new_batch):
        next_discussion_id = discussion_id + 1
        if next_discussion_id == len(new_batch):
            next_discussion_id = 0
        db.execute(
            """INSERT INTO discussionTask 
            (site_id, journal_oid, responsibility, phase, batch_id, discussion_id, next_discussion_id, evidence_username, reconsider_username) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (disagreement['site_id'], disagreement['journal_oid'], responsibility, "reconsider", batch_id, discussion_id,
             next_discussion_id, evidence_username, reconsider_username)
        )

    db.commit()

    print(f"Created new batch of {len(new_batch)} Reconsider tasks with batch_id {batch_id}.")

    return True


def get_existing_tasks(responsibility, current_user, other_user, phase):
    """
    Gets all of the existing tasks (both Evidence and Reconsider)

    :param responsibility:
    :param current_user:
    :param other_user:
    :param phase:
    :return:
    """
    evidence_username = current_user if phase == "evidence" else other_user
    reconsider_username = other_user if phase == "evidence" else current_user

    db = get_db()

    # First, we query to identify this phase's tasks in the database
    task_df = pd.read_sql_query(
        """SELECT *
            FROM discussionTask 
            WHERE responsibility = ? AND evidence_username = ? AND reconsider_username = ? AND phase = ?
                AND batch_id = (SELECT MAX(batch_id) FROM discussionTask 
                WHERE responsibility = ? AND evidence_username = ? AND reconsider_username = ? AND phase = ?)
            GROUP BY discussion_id
            ORDER BY id DESC""", db, index_col="id",
        params=(responsibility, evidence_username, reconsider_username, phase,
                responsibility, evidence_username, reconsider_username, phase))
    if len(task_df) == 0:
        return None

    # Next, we want to fill in if each task is complete or not
    # In other words, is there a DiscussionEntry corresponding to this DiscussionTask
    batch_id = int(task_df.iloc[0]['batch_id'])  # pull the batch_id to match on
    cursor = db.execute(
        """SELECT discussion_id, highlighted_text, additional_discussion, is_annotation_changed
            FROM discussionEntry 
            WHERE responsibility = ? AND evidence_username = ? AND reconsider_username = ? AND phase = ? AND batch_id = ?
            GROUP BY discussion_id
            ORDER BY id DESC""",
        (responsibility, evidence_username, reconsider_username, phase, batch_id))
    results = cursor.fetchall()
    assert len(results) <= len(task_df)
    task_df["is_complete"] = False
    for row in results:
        if phase == "evidence":
            # we only consider a task to be complete
            # if it has provided at least one piece of evidence
            highlighted_text, additional_discussion, is_annotation_changed = row['highlighted_text'], row['additional_discussion'], row['is_annotation_changed']
            if (highlighted_text is None or highlighted_text.strip() == "") and (additional_discussion is None or additional_discussion.strip() == "") and is_annotation_changed == 0:
                # In other words, they didn't change their mind on the annotation but also didn't highlight any text or provide any additional discussion.
                continue
        discussion_id = row['discussion_id']
        task_df.loc[task_df["discussion_id"] == discussion_id, "is_complete"] = True
    
    return task_df


# TODO Fix this import for this code, which is copied from annotation_data.responsibility
responsibility_labels = ["communicating", "info_filtering", "clinical_decisions", "preparation", "symptom_management",
                         "support_management", "coordinating_support", "sharing_medical_info", "compliance",
                         "managing_transitions", "financial_management", "continued_monitoring", "giving_back",
                         "behavior_changes"]
responsibility_labels_with_none = responsibility_labels + ["none"]


def sort_responsibility_list(responsibility_list):
    return sorted(responsibility_list, key=lambda responsibility: responsibility_labels_with_none.index(responsibility))


def get_labels_from_responsibility_string(responsibility_string, include_none=False, warn_on_legacy_responsibilities=True):
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


def get_responsibility_annotations_by_username():
    db = get_db()
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
