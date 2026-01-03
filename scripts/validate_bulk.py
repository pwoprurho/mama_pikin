import csv
import sys

REQUIRED = ['Patient Name','Patient Phone','State','LGA']

csv_path = '..\\bulk.csv' if __name__ == '__main__' else 'bulk.csv'
# Adjust path to run from project root when executed via terminal
csv_path = 'bulk.csv'

missing_column_rows = []
invalid_phone_rows = []
rows = []

with open(csv_path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames or []
    for col in REQUIRED:
        if col not in headers:
            print(f"ERROR: Missing required column: {col}")
            sys.exit(2)

    for i, row in enumerate(reader, start=2):
        rows.append((i, row))

for lineno, row in rows:
    missing = [c for c in REQUIRED if not row.get(c) or str(row.get(c)).strip()=='']
    if missing:
        missing_column_rows.append((lineno, missing))
        continue

    phone = str(row['Patient Phone']).strip()
    phone_digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(phone_digits) == 10 and not phone_digits.startswith('0'):
        phone_digits = '0' + phone_digits
    # now expect 11 digits starting with 0
    if not (len(phone_digits) == 11 and phone_digits.startswith('0')):
        invalid_phone_rows.append((lineno, row['Patient Phone']))

print('Bulk CSV Validation Report')
print('--------------------------')
print(f'Total rows processed: {len(rows)}')
print(f'Rows with missing required columns: {len(missing_column_rows)}')
if missing_column_rows:
    for ln, miss in missing_column_rows:
        print(f'  Line {ln}: missing {miss}')
print(f'Rows with invalid phone: {len(invalid_phone_rows)}')
if invalid_phone_rows:
    for ln, ph in invalid_phone_rows:
        print(f'  Line {ln}: phone value "{ph}"')

if not missing_column_rows and not invalid_phone_rows:
    print('\nSanity check passed: CSV looks good for upload.')
    sys.exit(0)
else:
    print('\nSanity check found issues. Fix the rows above before uploading.')
    sys.exit(1)
