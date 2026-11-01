"""Build backend/app/geodata/locations.json.gz: regions and cities per country for the address forms.

Source: GeoNames (https://www.geonames.org, CC BY 4.0), first-level administrative divisions
(admin1CodesASCII.txt) and all places with at least 1,000 inhabitants (cities1000.txt).
    curl -O https://download.geonames.org/export/dump/cities1000.zip && unzip cities1000.zip
    curl -O https://download.geonames.org/export/dump/admin1CodesASCII.txt
    python -I scripts/build_locations.py cities1000.txt admin1CodesASCII.txt
Output: {"CC": {"regions": {"code": "name"}, "cities": [["name", "region code", ["alias", ...]], ...]}}.
GeoNames names large cities by their English exonym ("Turin"); aliases keep the local and other Latin-script
names ("Torino") so typing them finds the city. Only cities of 50,000+ inhabitants get aliases (smaller places
already carry their local name), at most 16 each.
"""
import gzip, json, re, sys, unicodedata
from pathlib import Path

LATIN_WORD = re.compile(r"^[^\W\d_][^\W\d_' .-]*(?:[' .-][^\W\d_]+)*$")
def fold(s): return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().casefold()
def latin(s): return all(unicodedata.name(c, '').startswith(('LATIN', 'SPACE', 'HYPHEN', 'APOSTROPHE', 'FULL STOP')) or c in "'-. " for c in s)

def aliases(name, alternates, population):
    if population < 50000: return []
    seen, result = {fold(name)}, []
    for alias in alternates.split(','):
        alias = alias.strip()
        if not (3 <= len(alias) <= 40) or alias.isupper() or not alias[:1].isupper() or not LATIN_WORD.match(alias) or not latin(alias): continue
        if fold(alias) in seen: continue
        seen.add(fold(alias)); result.append(alias)
    return result[:16]

def main(cities_path, admin1_path, output=Path(__file__).resolve().parents[1] / 'backend/app/geodata/locations.json.gz'):
    data = {}
    for line in Path(admin1_path).read_text(encoding='utf-8').splitlines():
        code, name, *_ = line.split('\t')
        country, region = code.split('.', 1)
        data.setdefault(country, {'regions': {}, 'cities': []})['regions'][region] = name
    for line in Path(cities_path).read_text(encoding='utf-8').splitlines():
        f = line.split('\t')
        # name, alternate names, feature class P (populated place), country, admin1 code, population
        if f[6] != 'P': continue
        entry = data.setdefault(f[8], {'regions': {}, 'cities': []})
        entry['cities'].append([f[1], f[10] if f[10] in entry['regions'] else '', aliases(f[1], f[3], int(f[14] or 0))])
    for entry in data.values():
        unique = {}
        for name, region, alias in entry['cities']: unique.setdefault((name, region), alias)
        entry['cities'] = [[n, r, a] if a else [n, r] for (n, r), a in sorted(unique.items(), key=lambda c: (fold(c[0][0]), c[0][1]))]
        entry['regions'] = dict(sorted(entry['regions'].items(), key=lambda r: fold(r[1])))
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, 'wt', encoding='utf-8', compresslevel=9) as out:
        json.dump(data, out, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print(f'{output}: {len(data)} countries, {sum(len(e["cities"]) for e in data.values())} cities, {output.stat().st_size} bytes')

if __name__ == '__main__':
    main(*sys.argv[1:3])
