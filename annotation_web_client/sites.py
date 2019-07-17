from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, make_response
)
from werkzeug.exceptions import abort

from annotation_web_client.auth import login_required
from annotation_web_client.db import get_db
from annotation_web_client.annotate import set_journal_annotation, get_journal_annotation
from annotation_web_client.prediction import get_journal_prediction, get_journal_predictions
from annotation_web_client.site_df import get_site_df, get_journals, get_journals_user_dict

import json
import os
import re
from html.parser import HTMLParser
import itertools
from datetime import datetime
import multiprocessing as mp
from nltk import word_tokenize
from IPython.core.display import display, HTML
import datetime as dt
import pytz
import numpy as np

bp = Blueprint('sites', __name__)

VIEW_LIMIT = 50


@bp.route('/', methods=('GET', 'POST'))
def index():
    if request.method == 'POST':
        redirect_url = url_for('index',
                               sortBy=request.form['sortBy'],
                               sortOrder=request.form.get('sortOrder', 'descending'),  # if not checked, sort descending
                               query=request.form.get('query', '')
                               )
        return redirect(redirect_url)

    site_df = get_site_df()

    filtered_df = site_df

    # Filtering
    query_str = request.args.get('query', '')
    if query_str.strip() != "":
        print(query_str)
        locals = {}
        locals['nan'] = np.nan
        locals['invalid'] = [np.nan, None, '', -1]
        locals['oneYear'] = 1000 * 60 * 60 * 24 * 365
        for i in range(0, 15):
            year = 2004 + i
            locals['year%d' % year] = dt.datetime(year=year, month=1, day=1).timestamp() * 1000
        if "description.str." in query_str:
            # If the user is trying to invoke a string method on the site description,
            # need to use the python eval engine and need to not include NAs...
            # FIXME This is kind of a nasty hack, and should definitely be updated in the future.
            filtered_df = filtered_df[filtered_df["description"].notna()]
            filtered_df = filtered_df.query(query_str, local_dict=locals, engine="python")
        else:
            filtered_df = filtered_df.query(query_str, local_dict=locals)

    # Sorting
    sort_by_col = request.args.get('sortBy', '')
    sort_order = request.args.get('sortOrder', 'ascending')
    sort_ascending = sort_order == 'ascending'
    if sort_by_col.strip() != "":
        if sort_by_col in site_df.columns:
            filtered_df = filtered_df.sort_values(by=sort_by_col, ascending=sort_ascending)
        else:
            raise KeyError("sortBy must be a column in the site dataframe.")

    total_site_count = len(filtered_df)
    # only take the first 50 sites for rendering
    sites = [filtered_df.iloc[i].to_dict() for i in range(min(VIEW_LIMIT, total_site_count))]
    return render_template('sites/index.html',
                           sites=sites,
                           total_site_count=total_site_count,
                           site_columns=sorted(list(site_df.columns)))


@bp.route('/siteId/<int:site_id>', methods=('GET', 'POST'))
def view_site(site_id, phase_conflict_list=[], responsibility_conflict_list=[], user1=None, user2=None):
    site_id = int(site_id)
    if request.method == 'POST':
        # save the value from the request

        journal_oid = None
        if 'journal_oid' in request.form:
            journal_oid = request.form['journal_oid']

        if 'note' in request.form:
            note_data = request.form["note"]
            if len(note_data) > 1000000:  # character limit for notes
                return make_response("Note too long to save.", 200)
            if not journal_oid:  # must have journal id with this annotation
                return make_response("Journal info not included in post request.", 200)
            set_journal_annotation('journal_note', site_id, journal_oid, note_data)

        if 'journal_author' in request.form:
            author_type = request.form['journal_author']
            if not journal_oid:  # must have journal id with this annotation
                return make_response("Journal info not included in post request.", 200)
            set_journal_annotation('journal_author_type', site_id, journal_oid, author_type)

        if 'journey_phases' in request.form:
            journey_phases = request.form['journey_phases']
            if not journal_oid:  # must have journal id with this annotation
                return make_response("Journal info not included in post request.", 200)
            set_journal_annotation('journal_journey_phase', site_id, journal_oid, journey_phases)

        if 'responsibilities' in request.form:
            responsibilities = request.form['responsibilities']
            if not journal_oid:  # must have journal id with this annotation
                return make_response("Journal info not included in post request.", 200)
            set_journal_annotation('journal_patient_responsibilities', site_id, journal_oid, responsibilities)

        return make_response("OK", 200)

    site = generate_site(site_id)
    if site:
        return render_template('sites/view.html',
                                   site=site,
                                   phase_conflict_list=phase_conflict_list,
                                   responsibility_conflict_list=responsibility_conflict_list,
                                   user1=user1,
                                   user2=user2)
    else:
        return "Unknown site."


def generate_site(site_id):
    """
    Generates the site dictionary from the site dataframe and loading in the journals
    :param site_id:
    :return: The site dictionary
    """
    site = None
    site_df = get_site_df()
    if site_df is not None:
        df_by_id = site_df[site_df["_id"] == site_id]
        if len(df_by_id) > 0:
            if len(df_by_id) > 1:
                print("Multiple entries for this siteId.")

            site = df_by_id.iloc[0].to_dict()
            print("Generating site:", site["_id"])

            site["healthCondition_repr"] = get_health_condition_repr(site)
            site["createdAt_repr"] = get_date_repr(site["createdAt"])
            site["updatedAt_repr"] = get_date_repr(site["updatedAt"])
            site["description"] = clean_html_text(site["description"] if site["description"] else "")

            journals = get_journals(site["_id"])
            site["journals"] = journals
            site["journal_count"] = len(site["journals"])
            user_dict = get_journals_user_dict(site["userId"] if "userId" in site else "", journals)
            for i, journal in enumerate(site["journals"]):
                journal['index'] = str(i + 1)
                journal['amp_count'] = len(journal["amps"]) if "amps" in journal else 0

                author_id = int(journal["userId"]) if "userId" in journal else "Unknown"
                journal['userId_repr'] = author_id
                journal['author_text'] = user_dict[author_id] if author_id in user_dict else "Unknown"

                journal_oid = journal["_id"]["$oid"]
                journal['journal_oid'] = journal_oid
                del journal["_id"]
                journal_id = journal["journalId"] if "journalId" in journal else "Unknown"
                if journal_id == "Unknown":
                    journal_id = journal_oid
                journal['journal_id'] = journal_id
                journal['body'] = clean_html_text(journal['body'] if 'body' in journal else "(no body)")

                journal['createdAt_repr'] = get_date_repr(journal["createdAt"]["$date"])
                journal['updatedAt_repr'] = get_date_repr(journal["updatedAt"]["$date"])

                replies = journal["replies"] if "replies" in journal else []
                journal['reply_count'] = len(replies)
                if len(replies) > 0:
                    replies = list(reversed(replies))
                    journal["replies"] = replies
                for reply_index, reply in enumerate(replies):
                    reply['index'] = reply_index + 1
                    reply['author_id'] = int(reply["userId"]) if "userId" in reply else "Unknown"
                    reply['amps_count'] = len(reply["amps"]) if "amps" in reply else 0
                    reply['createdAt_repr'] = reply["createdAt"] if "createdAt" in reply else "(Time unknown)"
                    reply['body'] = reply["body"] if "body" in reply else "(no body)"
                    reply['signature'] = reply["signature"] if "signature" in reply else "(no signature)"

                # Add model predictions that exist for this journal
                # First, add the author type prediction
                author_type, prob = get_journal_prediction('journal_author_type', site_id, journal_oid)
                if author_type is None:
                    journal['author_prediction_repr'] = "None"
                else:
                    journal['author_prediction_repr'] = "{} ({:.2})".format(author_type, prob)
                # Second, add the phase prediction
                journey_phase, prob = get_journal_prediction('journal_journey_phase', site_id, journal_oid)
                if journey_phase is None:
                    journal['journey_phase_repr'] = "None"
                else:
                    journal['journey_phase_repr'] = "{} ({:.2})".format(author_type, prob)

                # Add existing annotation data to journal if user is logged in
                if g.user:
                    journal['annotation'] = {}
                    journal['annotation']['note'] = get_journal_annotation('journal_note',
                                                                           site_id, journal_oid,
                                                                           default="")
                    journal['annotation']['author_type'] = get_journal_annotation('journal_author_type',
                                                                                  site_id, journal_oid)
                    journal['annotation']['journey_phases'] = get_journal_annotation('journal_journey_phase',
                                                                                     site_id, journal_oid)
                    journal['annotation']['responsibilities'] = get_journal_annotation(
                        'journal_patient_responsibilities',
                        site_id, journal_oid, default=""
                    )
    return site


def clean_html_text(description):
    # basic regex replacement of link destinations to a safe location
    cleaned_description = re.sub('href="[^"]+"', f'href="{url_for("index")}"', description, flags=re.MULTILINE)
    # replace many co-localed linebreaks with only 2 linebreaks
    cleaned_description = re.sub("<br><br>(<br>)+", "<br><br>", cleaned_description, flags=re.MULTILINE)
    return cleaned_description


def get_health_condition_repr(site):
    return f"{site['healthCondition_category']} ({site['healthCondition_name']})"


def get_date_repr(unix_time_ms, invalid_date_repr="n/a"):
    """
    :return a string representing the date, or invalid_date_repr if the date is invalid
    """
    #if type(unix_time_ms) != int:
    #    return invalid_date_repr

    # convert the date to unix time (i.e. seconds since the unix epoch)
    created_at_utc = unix_time_ms / 1000

    # convert the timestamp to a string
    unaware_datetime = datetime.utcfromtimestamp(created_at_utc)
    utc_datetime = unaware_datetime.replace(tzinfo=pytz.UTC)
    cst_datetime = utc_datetime.astimezone(tz=pytz.timezone("America/Chicago"))

    datetime_string = cst_datetime.strftime("%Y-%m-%d %H:%M") + " CST"
    return datetime_string