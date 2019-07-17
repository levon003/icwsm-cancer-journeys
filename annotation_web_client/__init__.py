import os

from flask import Flask

import sys
sys.path.append("../annotation_data")

VERSION = "0.0.1"


def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'cbAnnotator.sqlite'),
        JOURNAL_DATABASE="/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/extract_site_features/journal_metadata.db",
        ANNOTATION_DIR=os.path.join(app.instance_path, 'annotation_data'),
        HOSTNAME_FILE=os.path.join(app.instance_path, 'webclient_hostname.txt')
    )

    app.config.version = VERSION
    app.config.show_annotation_tools = True

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['ANNOTATION_DIR'], exist_ok=True)

    from . import db
    db.init_app(app)

    from . import journal_db
    journal_db.init_app(app)

    from . import annotate
    annotate.init_app(app)
    app.register_blueprint(annotate.bp)

    from . import site_df
    site_df.init_app(app)

    from . import auth
    app.register_blueprint(auth.bp)

    from . import sites
    app.register_blueprint(sites.bp)
    app.add_url_rule('/', endpoint='index')

    from . import conflict
    app.register_blueprint(conflict.bp)

    from . import responsibility_discussion
    app.register_blueprint(responsibility_discussion.bp)

    return app

application = create_app()
