from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, make_response
)
from werkzeug.exceptions import abort

from annotation_web_client.auth import login_required
from annotation_web_client.db import get_db
from annotation_web_client.annotate import get_journal_annotations
from annotation_web_client.site_df import get_site_df, get_journals, get_journals_user_dict
from annotation_web_client.sites import view_site
from annotation_web_client.journal_db import get_journal_db

bp = Blueprint('conflict', __name__)


@bp.route('/conflict/journal/responsibilities/', methods=('GET',))
def view_journal_responsibility_conflict_summary():
    db = get_db()
    users = db.execute(
        'SELECT username FROM user'
    ).fetchall()
    username_list = [user['username'] for user in users]

    user_list = []
    for username in username_list:
        cursor = db.execute(
            """SELECT COUNT(*) AS responsibility_count FROM (
                SELECT site_id, journal_oid 
                FROM journalAnnotation 
                WHERE username = ? AND annotation_type = ?
                GROUP BY site_id, journal_oid, annotation_type, username)""",
            (username, 'journal_patient_responsibilities'))
        responsibility_count = cursor.fetchone()['responsibility_count']
        if responsibility_count > 0:
            user_list.append({'username': username, 'responsibility_count': responsibility_count})
    user_list.sort(key=lambda user: user['responsibility_count'], reverse=True)

    return render_template('conflict/journalResponsibilityConflictSummary.html', annotator_list=user_list)


@bp.route('/conflict/journal/responsibilities/<user1>/vs/<user2>', methods=('GET',))
def view_journal_responsibility_conflicts(user1, user2):
    try:
        responsibilities1 = get_journal_annotations('journal_patient_responsibilities', user1)
        responsibilities2 = get_journal_annotations('journal_patient_responsibilities', user2)
    except:
        return f"Failed to load journal phase annotations for users '{user1}' and '{user2}'."

    journal_db = get_journal_db()

    responsibility_dict1 = {}
    responsibility_dict2 = {}
    for responsibility_annotation in responsibilities1:
        key = f"{responsibility_annotation['site_id']}|{responsibility_annotation['journal_oid']}"
        responsibility_dict1[key] = responsibility_annotation['data']
    for responsibility_annotation in responsibilities2:
        key = f"{responsibility_annotation['site_id']}|{responsibility_annotation['journal_oid']}"
        responsibility_dict2[key] = responsibility_annotation['data']

    conflict_list = []
    common_journal_keys = set(responsibility_dict1.keys()).intersection(set(responsibility_dict2.keys()))
    for key in common_journal_keys:
        data1 = responsibility_dict1[key]
        data2 = responsibility_dict2[key]
        r1 = set(data1.split("|"))
        r2 = set(data2.split("|"))

        if r1 != r2:
            # this is a conflict
            site_id, journal_oid = key.split("|")

            in_common = ", ".join(list(r1 & r2))
            user1_only = ", ".join(list(r1 - r2))
            user2_only = ", ".join(list(r2 - r1))

            journal_index = journal_db.execute("""
            SELECT site_index 
                FROM journalMetadata 
                WHERE site_id = ? AND journal_oid = ?
            """, (site_id, journal_oid)).fetchone()['site_index']

            resolution = get_journal_annotation_conflict_resolution('journal_patient_responsibilities',
                                                                    site_id,
                                                                    journal_oid)
            resolved = False
            correct_username = ""
            if resolution is not None:
                # Only consider the situation resolved if a correct username was provided
                resolved = resolution['resolution_type'] == 'username'
                if resolved:
                    correct_username = resolution['correct_username'].strip()

            conflict = {"site_id": site_id,
                        "journal_oid": journal_oid,
                        "journal_index": journal_index,
                        "user1_responsibility_list": r1,
                        "user2_responsibility_list": r2,
                        "in_common": in_common,
                        "user1_only": user1_only,
                        "user2_only": user2_only,
                        "conflict_resolved": resolved,
                        "correct_username": correct_username
                        }
            conflict_list.append(conflict)

    # sort the conflict_list based on the site_id and the journal_index
    conflict_list.sort(key=lambda conflict: (conflict['site_id'], conflict['journal_index']))

    return render_template('conflict/journalResponsibilityConflictPair.html',
                           user1=user1,
                           user2=user2,
                           conflict_list=conflict_list)


@bp.route('/conflict/journal/responsibilities/<user1>/vs/<user2>/site/<int:site_id>', methods=('GET', 'POST'))
def view_site_journal_responsibility_conflicts(user1, user2, site_id):
    if request.method == 'POST':
        # intercept POSTs that are for conflict-resolution of journal phase annotations

        if 'conflict_type' in request.form and request.form['conflict_type'] == 'journal_patient_responsibilities':
            journal_oid = request.form['journal_oid']
            correct_username = request.form['correct_username']
            set_journal_annotation_conflict_resolution('journal_patient_responsibilities',
                                                       site_id,
                                                       journal_oid,
                                                       correct_username)
            return make_response("OK", 200)

        # This isn't a conflict-resolution post, so let view_site handle it.
        return view_site(site_id)

    # This is a GET request
    try:
        responsibilities1 = get_journal_annotations('journal_patient_responsibilities', user1)
        responsibilities2 = get_journal_annotations('journal_patient_responsibilities', user2)
    except:
        return f"Failed to load journal phase annotations for users '{user1}' and '{user2}'."

    journal_db = get_journal_db()

    responsibility_dict1 = {}
    responsibility_dict2 = {}
    for responsibility_annotation in responsibilities1:
        if responsibility_annotation['site_id'] != site_id:
            continue
        key = responsibility_annotation['journal_oid']
        responsibility_dict1[key] = responsibility_annotation['data']
    for responsibility_annotation in responsibilities2:
        if responsibility_annotation['site_id'] != site_id:
            continue
        key = responsibility_annotation['journal_oid']
        responsibility_dict2[key] = responsibility_annotation['data']

    conflict_list = []
    common_journal_keys = set(responsibility_dict1.keys()).intersection(set(responsibility_dict2.keys()))
    for key in common_journal_keys:
        data1 = responsibility_dict1[key]
        data2 = responsibility_dict2[key]
        r1 = set(data1.split("|"))
        r2 = set(data2.split("|"))

        if r1 != r2:
            # this is a conflict
            journal_oid = key

            in_common = ", ".join(list(r1 & r2))
            user1_only = ", ".join(list(r1 - r2))
            user2_only = ", ".join(list(r2 - r1))

            journal_index = journal_db.execute("""
                SELECT site_index 
                    FROM journalMetadata 
                    WHERE site_id = ? AND journal_oid = ?
                """, (site_id, journal_oid)).fetchone()['site_index']

            resolution = get_journal_annotation_conflict_resolution('journal_patient_responsibilities',
                                                                  site_id,
                                                                  journal_oid)
            resolved = False
            correct_username = ""
            if resolution is not None:
                # Only consider the situation resolved if a correct username was provided
                resolved = resolution['resolution_type'] == 'username'
                if resolved:
                    correct_username = resolution['correct_username'].strip()

            conflict = {"site_id": site_id,
                        "journal_oid": journal_oid,
                        "journal_index": journal_index,
                        "user1_responsibility_list": data1,
                        "user2_responsibility_list": data2,
                        "in_common": in_common,
                        "user1_only": user1_only,
                        "user2_only": user2_only,
                        "conflict_resolved": resolved,
                        "correct_username": correct_username}
            conflict_list.append(conflict)

    # sort the conflict_list based on the site_id and the journal_index
    conflict_list.sort(key=lambda conflict: (conflict['site_id'], conflict['journal_index']))

    return view_site(site_id, user1=user1, user2=user2, responsibility_conflict_list=conflict_list)


@bp.route('/conflict/journal/phases/', methods=('GET',))
def view_journal_phase_conflict_summary():
    db = get_db()
    users = db.execute(
        'SELECT username FROM user'
    ).fetchall()
    username_list = [user['username'] for user in users]

    user_list = []
    for username in username_list:
        cursor = db.execute(
            """SELECT COUNT(*) AS phase_count FROM (
                SELECT site_id, journal_oid 
                FROM journalAnnotation 
                WHERE username = ? AND annotation_type = ?
                GROUP BY site_id, journal_oid, annotation_type, username)""",
            (username, 'journal_journey_phase'))
        phase_count = cursor.fetchone()['phase_count']
        if phase_count > 0:
            user_list.append({'username': username, 'phase_count': phase_count})
    user_list.sort(key=lambda user: user['phase_count'], reverse=True)

    return render_template('conflict/journalPhaseConflictSummary.html', annotator_list=user_list)

@bp.route('/conflict/journal/phases/<user1>/vs/<user2>', methods=('GET',))
def view_journal_phase_conflicts(user1, user2):
    try:
        phases1 = get_journal_annotations('journal_journey_phase', user1)
        phases2 = get_journal_annotations('journal_journey_phase', user2)
    except:
        return f"Failed to load journal phase annotations for users '{user1}' and '{user2}'."

    journal_db = get_journal_db()

    phase_dict1 = {}
    phase_dict2 = {}
    for phase_annotation in phases1:
        key = f"{phase_annotation['site_id']}|{phase_annotation['journal_oid']}"
        phase_dict1[key] = phase_annotation['data']
    for phase_annotation in phases2:
        key = f"{phase_annotation['site_id']}|{phase_annotation['journal_oid']}"
        phase_dict2[key] = phase_annotation['data']

    conflict_list = []
    common_journal_keys = set(phase_dict1.keys()).intersection(set(phase_dict2.keys()))
    for key in common_journal_keys:
        data1 = phase_dict1[key]
        data2 = phase_dict2[key]
        p1 = set(data1.split("|"))
        p2 = set(data2.split("|"))
        if "unknown" in p1:
            p1.remove("unknown")
        if "unknown" in p2:
            p2.remove("unknown")

        if p1 != p2:
            # this is a conflict
            site_id, journal_oid = key.split("|")

            in_common = ", ".join(list(p1 & p2))
            user1_only = ", ".join(list(p1 - p2))
            user2_only = ", ".join(list(p2 - p1))

            journal_index = journal_db.execute("""
            SELECT site_index 
                FROM journalMetadata 
                WHERE site_id = ? AND journal_oid = ?
            """, (site_id, journal_oid)).fetchone()['site_index']

            resolution = get_journal_annotation_conflict_resolution('journal_journey_phase',
                                                                    site_id,
                                                                    journal_oid)
            resolved = False
            correct_username = ""
            if resolution is not None:
                # Only consider the situation resolved if a correct username was provided
                resolved = resolution['resolution_type'] == 'username'
                if resolved:
                    correct_username = resolution['correct_username'].strip()

            conflict = {"site_id": site_id,
                        "journal_oid": journal_oid,
                        "journal_index": journal_index,
                        "user1_phase_list": p1,
                        "user2_phase_list": p2,
                        "in_common": in_common,
                        "user1_only": user1_only,
                        "user2_only": user2_only,
                        "conflict_resolved": resolved,
                        "correct_username": correct_username
                        }
            conflict_list.append(conflict)

    # sort the conflict_list based on the site_id and the journal_index
    conflict_list.sort(key=lambda conflict: (conflict['site_id'], conflict['journal_index']))

    return render_template('conflict/journalPhaseConflictPair.html',
                           user1=user1,
                           user2=user2,
                           conflict_list=conflict_list)


@bp.route('/conflict/journal/phases/<user1>/vs/<user2>/site/<int:site_id>', methods=('GET', 'POST'))
def view_site_journal_phase_conflicts(user1, user2, site_id):
    if request.method == 'POST':
        # intercept POSTs that are for conflict-resolution of journal phase annotations

        if 'conflict_type' in request.form and request.form['conflict_type'] == 'journal_journey_phase':
            journal_oid = request.form['journal_oid']
            correct_username = request.form['correct_username']
            set_journal_annotation_conflict_resolution('journal_journey_phase',
                                                       site_id,
                                                       journal_oid,
                                                       correct_username)
            return make_response("OK", 200)

        # This isn't a conflict-resolution post, so let view_site handle it.
        return view_site(site_id)

    # This is a GET request
    try:
        phases1 = get_journal_annotations('journal_journey_phase', user1)
        phases2 = get_journal_annotations('journal_journey_phase', user2)
    except:
        return f"Failed to load journal phase annotations for users '{user1}' and '{user2}'."

    journal_db = get_journal_db()

    phase_dict1 = {}
    phase_dict2 = {}
    for phase_annotation in phases1:
        if phase_annotation['site_id'] != site_id:
            continue
        key = phase_annotation['journal_oid']
        phase_dict1[key] = phase_annotation['data']
    for phase_annotation in phases2:
        if phase_annotation['site_id'] != site_id:
            continue
        key = phase_annotation['journal_oid']
        phase_dict2[key] = phase_annotation['data']

    conflict_list = []
    common_journal_keys = set(phase_dict1.keys()).intersection(set(phase_dict2.keys()))
    for key in common_journal_keys:
        data1 = phase_dict1[key]
        data2 = phase_dict2[key]
        p1 = set(data1.split("|"))
        p2 = set(data2.split("|"))
        if "unknown" in p1:
            p1.remove("unknown")
        if "unknown" in p2:
            p2.remove("unknown")

        if p1 != p2:
            # this is a conflict
            journal_oid = key

            in_common = ", ".join(list(p1 & p2))
            user1_only = ", ".join(list(p1 - p2))
            user2_only = ", ".join(list(p2 - p1))

            journal_index = journal_db.execute("""
                SELECT site_index 
                    FROM journalMetadata 
                    WHERE site_id = ? AND journal_oid = ?
                """, (site_id, journal_oid)).fetchone()['site_index']

            resolution = get_journal_annotation_conflict_resolution('journal_journey_phase',
                                                                  site_id,
                                                                  journal_oid)
            resolved = False
            correct_username = ""
            if resolution is not None:
                # Only consider the situation resolved if a correct username was provided
                resolved = resolution['resolution_type'] == 'username'
                if resolved:
                    correct_username = resolution['correct_username'].strip()

            conflict = {"site_id": site_id,
                        "journal_oid": journal_oid,
                        "journal_index": journal_index,
                        "user1_phase_list": data1,
                        "user2_phase_list": data2,
                        "in_common": in_common,
                        "user1_only": user1_only,
                        "user2_only": user2_only,
                        "conflict_resolved": resolved,
                        "correct_username": correct_username}
            conflict_list.append(conflict)

    # sort the conflict_list based on the site_id and the journal_index
    conflict_list.sort(key=lambda conflict: (conflict['site_id'], conflict['journal_index']))

    return view_site(site_id, user1=user1, user2=user2, phase_conflict_list=conflict_list)


def get_journal_annotation_conflict_resolution(annotation_type, site_id, journal_oid, default=None):
    db = get_db()
    cursor = db.execute("""
                    SELECT *
                        FROM journalAnnotationConflictResolution 
                        WHERE site_id = ? AND journal_oid = ? AND annotation_type = ?
                        ORDER BY id DESC
                    """, (site_id, journal_oid, annotation_type))
    resolution = cursor.fetchone()
    if resolution is not None:
        return resolution
    else:
        return default


def set_journal_annotation_conflict_resolution(annotation_type, site_id, journal_oid, correct_username, resolving_username=None, commit=True):
    if resolving_username is None:
        if g.user is not None:
            resolving_username = g.user['username']
        else:
            raise ValueError(f"No active user while trying to set journal annotation conflict resolution '{annotation_type}'.")

    resolution_type = 'username'

    db = get_db()
    db.execute(
        """INSERT INTO journalAnnotationConflictResolution 
          (site_id, journal_oid, resolving_username, annotation_type, resolution_type, correct_username)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (site_id, journal_oid, resolving_username, annotation_type, resolution_type, correct_username)
    )
    if commit:
        db.commit()
