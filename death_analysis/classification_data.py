import csv, random

df1 = []
shuffled = []

FILENAME = '58363_results.csv'
DATASET_SIZE = 10

with open('data/EOL/'+FILENAME) as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
    next(csv_reader, None)
    line_count = 0
    for row in csv_reader:
        df1.append(int(row[0]))
        
for x in range(DATASET_SIZE):
    random_int = random.randint(0,len(df1)-1)
    shuffled.append(df1[random_int])
    df1.pop(random_int)
    
with open('data/EOL/shuffled_'+FILENAME, mode='w') as csv_file:
    employee_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    for x in shuffled:
        employee_writer.writerow([x])