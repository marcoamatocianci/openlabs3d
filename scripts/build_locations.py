"""Build backend/app/geodata/locations.json.gz: regions and cities per country for the address forms.

Source: GeoNames (https://www.geonames.org, CC BY 4.0), first-level administrative divisions
(admin1CodesASCII.txt) and all places with at least 15,000 inhabitants (cities15000.txt).
    curl -O https://download.geonames.org/export/dump/cities15000.zip && unzip cities15000.zip
    curl -O https://download.geonames.org/export/dump/admin1CodesASCII.txt
    python -I scripts/build_locations.py cities15000.txt admin1CodesASCII.txt
Output: {"CC": {"regions": {"code": "name"}, "cities": [["name", "region code"], ...]}}, sorted by name.
"""
import gzip, json, sys
from pathlib import Path

def main(cities_path, admin1_path, output=Path(__file__).resolve().parents[1] / 'backend/app/geodata/locations.json.gz'):
    data = {}
    for line in Path(admin1_path).read_text(encoding='utf-8').splitlines():
        code, name, *_ = line.split('\t')
        country, region = code.split('.', 1)
        data.setdefault(country, {'regions': {}, 'cities': []})['regions'][region] = name
    for line in Path(cities_path).read_text(encoding='utf-8').splitlines():
        f = line.split('\t')
        # name, feature class P (populated place), country code, admin1 code
        if f[6] != 'P': continue
        entry = data.setdefault(f[8], {'regions': {}, 'cities': []})
        entry['cities'].append([f[1], f[10] if f[10] in entry['regions'] else ''])
    for entry in data.values():
        entry['cities'] = sorted({tuple(c) for c in entry['cities']}, key=lambda c: (c[0].casefold(), c[1]))
        entry['regions'] = dict(sorted(entry['regions'].items(), key=lambda r: r[1].casefold()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, 'wt', encoding='utf-8', compresslevel=9) as out:
        json.dump(data, out, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print(f'{output}: {len(data)} countries, {sum(len(e["cities"]) for e in data.values())} cities, {output.stat().st_size} bytes')

if __name__ == '__main__':
    main(*sys.argv[1:3])
