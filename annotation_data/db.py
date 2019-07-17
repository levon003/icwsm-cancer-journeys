
import sqlite3
import os


def get_annotation_db():  # the web client's primary database, containing annotation info
    web_client_dir = "/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/instance/"
    annotation_web_client_database = os.path.join(web_client_dir, "cbAnnotator.sqlite")
    db = sqlite3.connect(
            annotation_web_client_database,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
    db.row_factory = sqlite3.Row
    return db


def get_journal_db():  # database containing journal info, including text
    journal_wd = "/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/extract_site_features"
    db_filename = os.path.join(journal_wd, "journal.db")
    db = sqlite3.connect(
        db_filename,
        detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row
    return db


def get_journal_info_db():  # database containing journal info, including text
    journal_wd = "/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/extract_site_features"
    db_filename = os.path.join(journal_wd, "journal_metadata.db")
    db = sqlite3.connect(
        db_filename,
        detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row
    return db
