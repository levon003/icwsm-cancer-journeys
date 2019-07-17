import csv

def list_to_csv(filename,list1):
    with open(filename, "w") as output:
        writer = csv.writer(output, lineterminator='\n')
        for val in list1:
                writer.writerow([val])