import argparse
import csv
import itertools

from geojson import dumps, Feature, FeatureCollection, LineString, Polygon
from pygeodesy.ellipsoidalVincenty import LatLon

def latlon(str):
    dm, m = str[:-1].split(".")
    deg = int(dm[:-2]) + int(dm[-2:]) / 60 + int(m) / 60000

    if str[-1] in "SW":
        deg = -deg

    return deg

def parse_cup(cup_file):
    # Skip TP header
    cup_file.readline()

    # Parse turnpoints
    cup = csv.reader(cup_file)
    wps = {t[0]: LatLon(latlon(t[3]), latlon(t[4]))
        for t in itertools.takewhile(lambda x: len(x) > 1, cup)}

    # Read task info
    info = list(cup)

    # Task description
    description = info.pop(0)
    task = [{'name': tp, 'pos': wps[tp]}
        for tp in description[1:] if tp in wps]

    # Read (optional) options
    if info[0][0].startswith("Options"):
        options = info.pop(0)

    # Convert observation line parameters to dict
    obs = [dict([x.split("=") for x in o]) for o in info]

    # Return merged TPs and OZs
    return [t | v for t, v in zip(task, obs)]

def task_feature(task, class_name):
    coords = [(t['pos'].lon, t['pos'].lat) for t in task]
    task = LineString(coords)

    feature = Feature(geometry=task, properties={'class': class_name})
    return feature

def make_line(tp, ang):
    radius = int(tp['R1'][:-1])
    return [tp['pos'].destination(radius, ang + 90),
            tp['pos'].destination(radius, ang - 90)]

def make_circle(tp):
    radius = int(tp['R1'][:-1])
    return [tp['pos'].destination(radius, a) for a in range(0, 360, 5)]

def make_sector(tp, ang):
    a1 = int(tp['A1'])
    r1 = int(tp['R1'][:-1])
    r2 = int(tp.get('R2', "0m")[:-1])

    start = ang - a1
    ang = [start + n for n in range(2 * a1 + 1)]

    coords = [tp['pos'].destination(r1, a) for a in ang]

    if r2:
        coords.extend([tp['pos'].destination(r2, a) for a in reversed(ang)])
    else:
        coords.append(tp['pos'])

    return coords

def zone_features(tps, class_name):
    features = []
    for n, tp in enumerate(tps):
        match tp['Style']:
            case "1":
                # Symmetrical
                ang1 = tp['pos'].compassAngleTo(tps[n-1]['pos'])
                ang2 = tp['pos'].compassAngleTo(tps[n+1]['pos'])

                ang = (ang1 + ang2) / 2
                if abs(ang2 - ang1) < 180:
                    ang = (ang + 180) % 360
            case "2":
                # To next
                ang = tp['pos'].compassAngleTo(tps[n+1]['pos'])
            case "3":
                # To previous
                ang = tp['pos'].compassAngleTo(tps[n-1]['pos'])

        if tp.get('Line') == "1":
            coords = make_line(tp, ang)
        elif tp['A1'] == "180":
            coords = make_circle(tp)
        else:
            coords = make_sector(tp, ang)

        obs = Polygon([[(c.lon, c.lat) for c in coords]])
        features.append(Feature(geometry=obs, properties={'class': class_name}))

    return features

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--cup_18m", help="18m class CUP file",
                        type=argparse.FileType("r"))
    parser.add_argument("--cup_std", help="Standard class CUP file",
                        type=argparse.FileType("r"))
    parser.add_argument("--cup_club", help="Club class CUP file",
                        type=argparse.FileType("r"))
    args = parser.parse_args()

    features = []

    if args.cup_18m:
        task = parse_cup(args.cup_18m)
        features.append(task_feature(task, "18m"))
        features.extend(zone_features(task, "18m"))

    if args.cup_std:
        task = parse_cup(args.cup_std)
        features.append(task_feature(task, "Standard"))
        features.extend(zone_features(task, "Standard"))

    if args.cup_club:
        task = parse_cup(args.cup_club)
        features.append(task_feature(task, "Club"))
        features.extend(zone_features(task, "Club"))

    collection = FeatureCollection(features)

    print(dumps(collection))
