import sqlite3

from flask import current_app, g


def get_journal_db():
    if 'journal_db' not in g:
        g.journal_db = sqlite3.connect(
            current_app.config['JOURNAL_DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.journal_db.row_factory = sqlite3.Row

    return g.journal_db


def close_db(e=None):
    db = g.pop('journal_db', None)

    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
