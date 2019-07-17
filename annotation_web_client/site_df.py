import pandas as pd

import click

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

site_df = None


def get_site_df():
    global site_df
    if site_df is None:
        feathered_site_df_filename = "/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/extract_site_features/site_scrubbed.df"
        try:
            site_df = pd.read_feather(feathered_site_df_filename)
        except Exception as ex:
            click.echo("Error reading feathered site data.")

    return site_df


def delete_site_df():
    global site_df
    site_df = None


@click.command('load-site-data')
def load_site_data_command():
    """Clear the existing data and create new tables."""
    get_site_df()
    click.echo('Loaded the site data.')


def init_app(app):
    app.cli.add_command(load_site_data_command)


def get_bucket_filename(siteId):
    # The bucket size used in bucket_journals_by_siteId, needed to recover the appropriate bucket filename
    bucket_size = 1000
    working_dir = "/home/srivbane/shared/caringbridge/data/projects/classify_health_condition/vw_experiments"
    sorted_journal_bucket_dir = os.path.join(working_dir, "sorted_journal_buckets")
    bucket_name = "Unknown"
    if siteId:
        bucket_name = siteId // bucket_size
    path = os.path.join(sorted_journal_bucket_dir, "siteId_{bucket_name}.json".format(bucket_name=bucket_name))
    return path if os.path.exists(path) else None


def get_journals(siteId):
    journal_filename = get_bucket_filename(siteId)
    journals = []
    awaiting_first_journal = True
    if journal_filename:
        with open(journal_filename, 'r', encoding="utf8") as infile:
            for line in infile:
                journal = json.loads(line.strip())
                journal_siteId = int(journal["siteId"]) if "siteId" in journal else None
                if journal_siteId == siteId:
                    journals.append(journal)
                    if awaiting_first_journal:
                        awaiting_first_journal = False
                elif not awaiting_first_journal:
                    # We have already looked at all of journals for this site
                    break
    return journals


def get_date_repr(date_dict, invalid_date_repr="n/a"):
    """
    :return a string representing the date, or invalid_date_repr if the date is invalid
    """

    # expect the date_dict to contain the date as a number in the "$date" field
    if "$date" not in date_dict:
        return invalid_date_repr

    # convert the date to unix time (i.e. seconds since the unix epoch)
    created_at_utc = date_dict["$date"] / 1000

    # convert the timestamp to a string
    unaware_datetime = datetime.utcfromtimestamp(created_at_utc)
    utc_datetime = unaware_datetime.replace(tzinfo=pytz.UTC)
    cst_datetime = utc_datetime.astimezone(tz=pytz.timezone("America/Chicago"))

    datetime_string = cst_datetime.strftime("%Y-%m-%d %H:%M") + " CST"
    return datetime_string


def get_reply_representation(index, reply_json, journal_author, user_dict):
    # include userId, signature, body, and amps count in the representation
    author_id = int(reply_json["userId"]) if "userId" in reply_json else "Unknown"
    amps_count = len(reply_json["amps"]) if "amps" in reply_json else 0
    post_date = reply_json["createdAt"] if "createdAt" in reply_json else "(Time unknown)"
    body = reply_json["body"] if "body" in reply_json else "(no body)"
    signature = reply_json["signature"] if "signature" in reply_json else "(no signature)"

    if author_id != "Unknown":
        if author_id in user_dict:
            author_id = "<b>%s</b> (id %d)" % (user_dict[author_id], author_id)
        elif author_id == journal_author:
            author_id = str(author_id) + " (OP)"

    reply_repr = """<b>Reply {index}</b> User {author_id} ({amps} amps) {post_date}<br>
                    {body}  --{signature}<br>
    """.format(
        index=index,
        author_id=author_id,
        amps=amps_count,
        post_date=post_date,
        body=body,
        signature=signature
    )
    return reply_repr


def get_journal_representation(index, journal_json, user_dict):
    journal = journal_json
    amp_count = len(journal["amps"]) if "amps" in journal else 0
    author_id = int(journal["userId"]) if "userId" in journal else "Unknown"
    author_text = user_dict[author_id] if author_id in user_dict else "Unknown"
    journal_id = journal["journalId"] if "journalId" in journal else "Unknown"
    if journal_id == "Unknown":
        journal_id = journal["_id"]["$oid"] if "_id" in journal else "Unknown"

    replies_count = len(journal["replies"]) if "replies" in journal else 0
    replies_repr = "<b>Comment count: {total_replies}</b><br>".format(total_replies=replies_count)
    if replies_count > 0:
        for i in range(replies_count):
            replies_repr += get_reply_representation(i + 1, journal["replies"][-(i + 1)], author_id, user_dict)

    body_text = journal["body"] if "body" in journal else "None"
    body_text = re.sub("<br><br>(<br>)+", "<br><br>", body_text, flags=re.MULTILINE)

    journal_repr = """<p>
    <b>Journal {index}</b><br>
    Title: <b>{title}</b><br>
    Journal Id: {journal_id}<br>
    Author: {author_text} (Id {author_id})<br>
    Amps: {amp_count}<br>
    Created: {createdAt}<br>
    Updated: {updatedAt}<br>
    {body}<br>
    <div style=\"padding-left: 20px;padding-right: 20px\">
    {replies}
    </div>
    </p>""".format(index=index,
                   body=body_text,
                   title=journal["title"] if "title" in journal else "None",
                   author_text=author_text,
                   author_id=author_id,
                   journal_id=journal_id,
                   createdAt=get_date_repr(journal["createdAt"] if "createdAt" in journal else {}),
                   updatedAt=get_date_repr(journal["updatedAt"] if "updatedAt" in journal else {}),
                   amp_count=amp_count,
                   replies=replies_repr)
    return journal_repr


def get_journals_user_set(journals):
    user_set = set()
    for journal in journals:
        author_id = int(journal["userId"]) if "userId" in journal else None
        if author_id:
            user_set.add(author_id)
    return user_set


def construct_journals_user_dict(site_author_id, user_set):
    user_dict = {}
    user_dict[site_author_id] = "Author 0"
    user_index = 1
    for user_id in user_set:
        if user_id not in user_dict:
            user_dict[user_id] = "Author %d" % user_index
            user_index += 1
    return user_dict


def get_journals_user_dict(site_user_id, journals):
    if len(journals) == 0:
        return {}
    user_set = get_journals_user_set(journals)
    user_dict = construct_journals_user_dict(site_user_id, user_set)
    return user_dict


def get_site_representation(site_json):
    site = site_json
    if "_id" in site and site["_id"] is not None:
        siteId = int(site["_id"])

        name = site["name"] if "name" in site else ""
        firstName = site["firstName"] if "firstName" in site else ""
        lastName = site["lastName"] if "lastName" in site else ""
        title = site["title"] if "title" in site else ""
        description = site["description"] if "description" in site else ""
        healthCondition = site["healthCondition"] if "healthCondition" in site else {}
        createdAt = site["createdAt"] if "createdAt" in site else {}
        updatedAt = site["updatedAt"] if "updatedAt" in site else {}
        visits = int(site["visits"]) if "visits" in site else None
        numJournals = int(site["numJournals"]) if "numJournals" in site else None
        numAmps = int(site["numAmps"]) if "numAmps" in site else None
        numTributes = int(site["numTributes"]) if "numTributes" in site else None
        numGuestbooks = int(site["numGuestbooks"]) if "numGuestbooks" in site else None
        numTasks = int(site["numTasks"]) if "numTasks" in site else None
        numPhotos = int(site["numPhotos"]) if "numPhotos" in site else None
        privacy = site["privacy"] if "privacy" in site else "unknown"
        userId = int(site["userId"]) if "userId" in site else -1

        health_condition_summary = "None reported"
        if "category" in healthCondition:
            health_condition_summary = healthCondition["category"]
            if "name" in healthCondition:
                health_condition_summary += " ({healthConditionName})".format(
                    healthConditionName=healthCondition["name"])

        summary_repr = """<p>
         <table>
        <tr><td>Health condition</td><td>{healthCondition}</td></tr>
        <tr><td>Privacy level</td><td>{privacy}</td></tr>
        <tr><td>Created</td><td>{createdAt}</td></tr>
        <tr><td>Updated</td><td>{updatedAt}</td></tr>
        <tr><td>Visits</td><td>{visits}</td></tr>
        </table>
        </p>""".format(createdAt=get_date_repr(createdAt),
                       updatedAt=get_date_repr(updatedAt),
                       privacy=privacy,
                       healthCondition=health_condition_summary,
                       visits=visits)

        journals = site["journals"] if "journals" in site else get_journals(siteId)
        journals_repr = "Total: {total_journals}<br>".format(total_journals=len(journals))
        if len(journals) > 0:
            user_set = get_journals_user_set(journals)
            user_dict = construct_journals_user_dict(userId, user_set)
            for i in range(len(journals)):
                journals_repr += get_journal_representation(i + 1, journals[i], user_dict)

        html_repr = """
        <h1>Site {siteId}</h1>

        <h3>Title: {title}</h3>

        <h3>Summary: </h3>
        {summary}

        <h3>Description:</h3>
        <div>
        {description}
        </div>

        <h3>Journals:</h3>
        {journals}
        """.format(siteId=siteId, title=title, description=description, summary=summary_repr, journals=journals_repr)

        return html_repr
