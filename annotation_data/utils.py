
import os


def get_webclient_url(site_id, journal_oid=None, port=5000):
    site_id = int(site_id)
    if journal_oid is not None:
        return 'http://127.0.0.1:%d/siteId/%d#%s' % (port, site_id, journal_oid)
    return 'http://127.0.0.1:%d/siteId/%d' % (port, site_id)


def get_valid_sites_filtered():
    return get_valid_sites("valid_classification_sites_filtered.txt")


def get_valid_sites_75percent():
    return get_valid_sites("valid_sites_with_75_pct_patient_journals.txt")


def get_valid_sites(site_filename):
    working_dir = "/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/identify_candidate_sites"
    valid_classification_sites_filename = os.path.join(working_dir, site_filename)
    with open(valid_classification_sites_filename, 'r') as infile:
        valid_sites = [int(line.strip()) for line in infile.readlines() if line.strip() != ""]
    return valid_sites
