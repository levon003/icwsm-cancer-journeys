#!/bin/bash -l
#PBS -l walltime=2:00:00,nodes=1:ppn=24,mem=250gb
#PBS -m abe
#PBS -M levon003@umn.edu
#PBS -N CaringBridge_convertJournalJsonToFeather
#PBS -o /home/srivbane/levon003/repos/qual-health-journeys/extract_site_features/pbs_job.stdout
#PBS -e /home/srivbane/levon003/repos/qual-health-journeys/extract_site_features/pbs_job.stderr 

working_dir="/home/srivbane/levon003/repos/qual-health-journeys/extract_site_features"
cd $working_dir
echo "In '$working_dir', running script."
python convertJournalJsonToFeather.py 
echo "Finished PBS script."

