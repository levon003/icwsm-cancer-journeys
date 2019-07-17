#!/bin/bash
# This script attempts to sync the current directory of annotation web client files with the target directory on MSI

TARGET_DIR="/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/annotation_web_client"

PWD=$( basename $( pwd ) )
if [ "$PWD" != "annotation_web_client" ]; then
    echo "Warning: Script should be run from the annotation_web_client directory.";
    exit 1;
fi

if [ -d "$TARGET_DIR" ]; then
    echo "Target directory found on local filesystem.";
    #cp -r . $TARGET_DIR ;
    rsync -av --exclude-from='.gitignore' ./ ${TARGET_DIR}/;
    DIFFS_REMAINING=$( diff -r -q /home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/annotation_web_client/ . | wc -l ) ;
    echo "Remaining differences: $DIFFS_REMAINING"
    echo "Sync complete." ;
    exit 0 ;
else
    echo "Not currently on MSI or target directory inaccessible. Attempting to SCP." ;
    echo "Not yet implemented!" ;
    exit 1 ;
fi
