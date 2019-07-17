import click
import os
import itertools
import functools
from flask import current_app, g

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, make_response
)
from werkzeug.exceptions import abort

from annotation_web_client.db import get_db
from annotation_web_client.auth import login_required
from annotation_web_client import create_app

bp = Blueprint('annotation', __name__)


@bp.route('/annotation/summary.html')
def annotation_summary():
    journal_notes = get_journal_annotations('journal_note')
    journal_author_types = get_journal_annotations('journal_author_type')
    journal_journey_phases = get_journal_annotations('journal_journey_phase')

    return render_template('annotation/summary.html',
                           journal_notes=journal_notes,
                           journal_author_types=journal_author_types,
                           journal_journey_phases=journal_journey_phases)


@bp.route('/annotation/<annotator_username>', methods=('GET', 'POST'))
def view_annotator_summary(annotator_username):
    def filter_by_username(annotation):
        return annotation['annotator_username'] == annotator_username

    journal_notes = get_journal_annotations('journal_note', username=annotator_username)
    journal_author_types = get_journal_annotations('journal_author_type', username=annotator_username)
    journal_journey_phases = get_journal_annotations('journal_journey_phase', username=annotator_username)
    journal_patient_responsibilities = get_journal_annotations('journal_patient_responsibilities',
                                                               username=annotator_username)

    annotated_site_ids = set()
    annotated_site_ids.update([a['site_id'] for a in journal_notes])
    annotated_site_ids.update([a['site_id'] for a in journal_author_types])
    annotated_site_ids.update([a['site_id'] for a in journal_journey_phases])
    annotated_site_ids.update([a['site_id'] for a in journal_patient_responsibilities])
    print(
        f"Found {len(annotated_site_ids)} existing site ids with at least one annotation by user '{annotator_username}'.")

    annotator_assignments = []
    if g.user and g.user['username'] == annotator_username:
        annotator_assignments = get_annotator_assignments(annotator_username,
                                                          journal_journey_phases=journal_journey_phases,
                                                          journal_patient_responsibilities=journal_patient_responsibilities,
                                                          annotated_site_ids=annotated_site_ids)

    return render_template('annotation/annotatorSummary.html',
                           username=annotator_username,
                           journal_notes=journal_notes,
                           journal_author_types=journal_author_types,
                           journal_journey_phases=journal_journey_phases,
                           journal_patient_responsibilities=journal_patient_responsibilities,
                           annotator_assignments=annotator_assignments,
                           annotated_site_ids=annotated_site_ids)


@bp.route('/annotation/responsibilityTagging.html')
def responsibility_tagging_note():
    return render_template('annotation/responsibilityTagging.html')


@bp.route('/annotation/phaseTagging.html')
def phase_tagging_note():
    return render_template('annotation/phaseTagging.html')


@bp.route('/annotation/journalFeed.html')
def view_journal_annotation_feed():
    journal_annotations = []

    db = get_db()
    cursor = db.execute(
        """SELECT site_id, journal_oid, username, annotation_type, created, id
            FROM journalAnnotation 
            ORDER BY id DESC LIMIT 500""")

    prev_id = None
    for row in cursor:
        annotation_id = row['id']
        annotation = {'id': annotation_id,
                      'site_id': row['site_id'],
                      'journal_oid': row['journal_oid'],
                      'username': row['username'],
                      'annotation_type': row['annotation_type'],
                      'date_repr': str(row['created'])}
        journal_annotations.append(annotation)

        # We check to make sure the ids are continguous,
        # as if they aren't that would indicate missing data.
        if prev_id is not None and prev_id - annotation_id != 1:
            raise ValueError(f"Missing ids! Gap between journal annotation ids {prev_id} and {annotation_id}.")
        prev_id = annotation_id
    return render_template('annotation/journalFeed.html', journal_annotations=journal_annotations)


def get_annotator_assignments(annotator_username,
                              journal_journey_phases=None,
                              journal_patient_responsibilities=None,
                              annotated_site_ids=None):
    # annotated_site_ids is used to determine if a site has previously been coded
    if annotated_site_ids is None:
        annotated_site_ids = []
        journal_journey_phases = []
        journal_patient_responsibilities = []
    user_annotation_assignment_dir = os.path.join(current_app.config['ANNOTATION_DIR'], 'assignments',
                                                  annotator_username)
    if not os.path.exists(user_annotation_assignment_dir):
        return []
    files = os.listdir(user_annotation_assignment_dir)
    assignment_list = []
    for filename in files:
        filepath = os.path.join(user_annotation_assignment_dir, filename)
        with open(filepath, 'r') as infile:
            lines = infile.readlines()
        header = lines[0]
        name = header.strip()
        site_ids = [int(line.strip()) for line in lines[1:] if line.strip() != "" and not line.strip().startswith('#')]
        site_coded = [site_id in annotated_site_ids for site_id in site_ids]
        site_journey_phase_counts = get_annotation_counts_by_site_id(site_ids, journal_journey_phases)
        site_patient_responsibility_counts = get_annotation_counts_by_site_id(site_ids,
                                                                              journal_patient_responsibilities)
        sites = [{"site_id": site_id,
                  "is_coded": is_coded,
                  "journey_phase_count": journey_phase_count,
                  "patient_responsibility_count": patient_responsibility_count}
                 for site_id, is_coded, journey_phase_count, patient_responsibility_count
                 in zip(site_ids,
                        site_coded,
                        site_journey_phase_counts,
                        site_patient_responsibility_counts)]
        assignment_dict = {"name": name, "sites": sites}
        assignment_list.append(assignment_dict)
    assignment_list.sort(key=lambda assignment_dict: assignment_dict['name'])
    return assignment_list


def get_annotation_counts_by_site_id(site_ids, annotations):
    def sort_by_site_id(annotation):
        return annotation['site_id']

    sorted_annotations = sorted(annotations, key=sort_by_site_id)
    annotation_site_groups = itertools.groupby(sorted_annotations, sort_by_site_id)

    annotation_counts = [0 for i in range(len(site_ids))]
    for site_id, site_annotations in annotation_site_groups:
        if site_id in site_ids:
            count_index = site_ids.index(site_id)
            annotation_count = len(list(site_annotations))
            annotation_counts[count_index] = annotation_count
    return annotation_counts


def get_journal_annotations(annotation_type, username=None):
    """
    :param annotation_type:
    :param filter_func:
    :param username:
    :return: List of annotation dictionaries with the following keys: site_id, journal_oid, annotator_username, data
    """

    data_list = []  # contains the annotations that will be returned
    db = get_db()
    if username is None:
        cursor = db.execute(
            """SELECT site_id, journal_oid, username, data 
                FROM journalAnnotation 
                WHERE annotation_type = ?
                GROUP BY site_id, journal_oid, annotation_type, username
                ORDER BY id DESC""", (annotation_type,))
    else:  # A username was specified
        cursor = db.execute(
            """SELECT site_id, journal_oid, username, data 
                FROM journalAnnotation 
                WHERE username = ? AND annotation_type = ?
                GROUP BY site_id, journal_oid, annotation_type, username
                ORDER BY id DESC""", (username, annotation_type))
    for row in cursor:
        annotation = {'site_id': row['site_id'],
                      'journal_oid': row['journal_oid'],
                      'annotator_username': row['username'],
                      'data': row['data']}
        if row['data'] != "":
            data_list.append(annotation)

    return data_list


def set_journal_annotation(annotation_type, site_id, journal_oid, value, username=None, commit=True):
    if username is None:
        if g.user is not None:
            username = g.user['username']
        else:
            raise ValueError(f"No active user while trying to set journal annotation '{annotation_type}'.")

    db = get_db()
    db.execute(
        'INSERT INTO journalAnnotation (site_id, journal_oid, username, annotation_type, data) VALUES (?, ?, ?, ?, ?)',
        (site_id, journal_oid, username, annotation_type, value)
    )
    if commit:
        db.commit()


def get_journal_annotation(annotation_type, site_id, journal_oid, default=None, username=None):
    if username is None:
        if g.user is not None:
            username = g.user['username']
        else:
            raise ValueError(f"No active user while trying to get journal annotation '{annotation_type}'.")

    db = get_db()
    cursor = db.execute(
        """SELECT data 
            FROM journalAnnotation 
            WHERE annotation_type = ? AND site_id = ? AND journal_oid = ? AND username= ?
            ORDER BY id DESC""", (annotation_type, site_id, journal_oid, username)
    )
    latest_annotation = cursor.fetchone()
    if latest_annotation is not None and latest_annotation['data'] != "":
        return latest_annotation['data']
    else:
        return default


@click.command('extract-annotation-shelves')
@click.argument('username')
def extract_shelves_to_csv_command(username):
    """
    This is a non-tested, likely deprecated extraction command that exists from when the annotations were
    stored in Python shelves.
    :param username: Username to pull annotations for.
    :return: None
    """
    click.echo('Extracting data from annotation shelves to CSV.')
    # usernames = ["luoxx498", "levon003"]

    # Annotation keys: site_id, journal_oid, annotator_username, data

    app = create_app()
    with app.app_context():
        filename = f"annotation_data_{username}.csv"
        annotation_data_csv = os.path.join(current_app.config['ANNOTATION_DIR'], 'export', filename)
        with open(annotation_data_csv, 'w') as outfile:
            header = "annotation_type,site_id,journal_oid,annotator_username,data\n"
            outfile.write(header)
            for annotation_type in ['journal_note', 'journal_author_type', 'journal_journey_phase']:
                annotations = get_journal_annotations(annotation_type, username=username)
                for annotation in annotations:
                    if "," in annotation['data']:
                        annotation['data'] = annotation['data'].replace(",", ";")
                    line = f"{annotation_type},{annotation['site_id']},{annotation['journal_oid']},{annotation['annotator_username']},{annotation['data']}\n"
                    outfile.write(line)
                click.echo(f'Finished extracting annotations of type "{annotation_type}" for user.')
            click.echo(f"Finished extracting annotations of all types for user '{username}'.")
    click.echo('Finished.')


@click.command('extract-annotations-to-csv')
def extract_annotations_to_csv_command():
    click.echo('Creating app context to execute CLI command.')
    app = create_app()
    with app.app_context():
        filename = f"annotation_data_complete.csv"
        annotation_data_csv = os.path.join(current_app.config['ANNOTATION_DIR'], 'export', filename)
        click.echo(f'Extracting annotations to CSV "{annotation_data_csv}".')
        with open(annotation_data_csv, 'w') as outfile:
            header = "annotation_type,site_id,journal_oid,annotator_username,data\n"
            outfile.write(header)
            for annotation_type in ['journal_note', 'journal_author_type', 'journal_journey_phase',
                                    'journal_patient_responsibilities']:
                annotations = get_journal_annotations(annotation_type)
                for annotation in annotations:
                    if "," in annotation['data']:
                        annotation['data'] = annotation['data'].replace(",", ";")
                    line = f"{annotation_type},{annotation['site_id']},{annotation['journal_oid']},{annotation['annotator_username']},{annotation['data']}\n"
                    outfile.write(line)
                click.echo(f'Finished extracting annotations of type "{annotation_type}".')
    click.echo('Finished.')


@click.command('insert-annotation-csv')
@click.argument('username')
@click.argument('filename')
def insert_csv_to_annotation_db_command(username, filename):
    click.echo(f'Inserting data from CSV "{filename}" to db as username "{username}".')

    # Assumed format of CSV is: annotation_type,site_id,journal_oid,annotator_username,data
    assert os.path.exists(filename)

    app = create_app()
    with app.app_context():
        db = get_db()
        lines_inserted = 0
        with open(filename, 'r') as infile:
            header_line = infile.readline()
            expected_header = "annotation_type,site_id,journal_oid,annotator_username,data\n"
            assert header_line == expected_header
            for line in infile:
                annotation_type, site_id, journal_oid, annotator_username, data = line.strip().split(",")
                set_journal_annotation(annotation_type, int(site_id), journal_oid, data, username, commit=False)
                lines_inserted += 1
                if lines_inserted % 100 == 0:
                    click.echo(f'Inserted "{lines_inserted}" lines from csv.')
        db.commit()
    click.echo('Finished.')


@click.command('extract-phase-annotations-to-csv')
def extract_phase_annotations_to_csv_command():
    """
    Extracts phase annotations to CSV, including merging in of conflicts.
    :return: None
    """
    click.echo('Creating app context to execute CLI command.')
    app = create_app()
    with app.app_context():
        filename = f"journal_journey_phase_annotations.csv"
        annotation_data_csv = os.path.join(current_app.config['ANNOTATION_DIR'], 'export', filename)
        click.echo(f'Extracting journey phase annotations to CSV "{annotation_data_csv}".')

        db = get_db()
        cursor = db.execute("""
            SELECT a.site_id, a.journal_oid, a.data, a.username, c.correct_username 
            FROM journalAnnotation a LEFT JOIN journalAnnotationConflictResolution c 
            ON a.site_id = c.site_id AND a.journal_oid = c.journal_oid AND a.annotation_type = c.annotation_type 
            WHERE a.annotation_type = "journal_journey_phase" AND a.data <> ""
            GROUP BY a.site_id, a.journal_oid, a.username 
            ORDER BY a.id DESC
        """)

        # Sort the returned annotations so that we can group by the individual journals
        def group_by_journal_function(row):
            return row['site_id'], row['journal_oid']

        all_rows = cursor.fetchall()
        all_rows.sort(key=group_by_journal_function)

        with open(annotation_data_csv, 'w') as outfile:
            header = "site_id,journal_oid,annotator_usernames,conflict_status,data\n"
            outfile.write(header)

            # group by the journals, writing a single line for each journal in the dataset
            for key, group in itertools.groupby(all_rows, group_by_journal_function):
                rows = list(group)
                site_id, journal_oid = key
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
                        assert data is not None
                    elif False in [combo[0]['data'] == combo[1]['data'] for combo in itertools.combinations(rows, 2)]:
                        # this annotation was not corrected and at least one pair of annotation differs from the others
                        conflict_status = "AMBIGUOUS"
                        data = ";".join([row['data'] for row in rows])
                    else:  # no conflict between annotators
                        conflict_status = "NO CONFLICT"
                        data = rows[0]['data']
                line = f"{site_id},{journal_oid},{annotator_usernames},{conflict_status},{data}\n"
                outfile.write(line)
        click.echo('Finished.')


def init_app(app):
    app.cli.add_command(extract_shelves_to_csv_command)
    app.cli.add_command(insert_csv_to_annotation_db_command)
    app.cli.add_command(extract_annotations_to_csv_command)
    app.cli.add_command(extract_phase_annotations_to_csv_command)
