# -*- coding: utf-8 -*-
"""
Prepares spatial data for the #CRNRAgoal tracking dashboard
- Downloads the Chattahoochee River geoJSON file
- Downloads the National Park Service hiking trails geoJSON file
  for the Chattahoochee River National Recreation Area (unit=CHAT)
- Creates a third file containing the river path as a single spatial object
- Creates a fourth file containing distance for each trail object
    - Calculates great-circle distance for each line segment within the trail
    - Sums distance for each object (GEOMETRYID)


Author: Kelly Gilbert
Created: 2020-11-09

Requirements:
  - pandas version 0.25.0 or higher for explode
  - geopandas
"""


import geopandas
import json
import numpy as np
from pandas import DataFrame, json_normalize
import requests
from shapely.geometry import MultiLineString


def split_multilinestring(geom_obj):
    """
    recursively split a MultiLineString into component lines
    """

    line_list = []
    for line in geom_obj:
        if line.geom_type == 'MultiLineString':
            line_list += split_multilinestring(line)
        else:
            line_list.append(line)
    return line_list


def haversine(o_lat, o_lon, d_lat, d_lon):
    """
    function to calculate great-circle distance using the Haversine formula
    https://en.wikipedia.org/wiki/Haversine_formula
    https://community.esri.com/groups/coordinate-reference-systems/blog/2017/10/05/haversine-formula
    
    inputs: origin lat/lon, destination lat/lon
    outputs: distance in miles
    """
    earth_radius = 3958.756    # radius of the earth, in miles
    
    o_lat, o_lon, d_lat, d_lon = map(np.deg2rad, [o_lat, o_lon, d_lat, d_lon])

    lat_diff = d_lat - o_lat
    lon_diff = d_lon - o_lon
    
    a = np.sin(lat_diff/2)**2 + np.cos(o_lat) \
        * np.cos(d_lat) * np.sin(lon_diff/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    d = earth_radius * c

    return d


river_file = 'rivers_streams_atlanta_region_chattahoochee.geojson'
river_file_merged = river_file.replace('.', '_merged.')
trails_file = 'nps_trails_web_mercator.geojson'
trails_file_dist = 'nps_trails_distance.csv'


#-------------------------------------------------------------------------------
# download the trail and river geojson files
#-------------------------------------------------------------------------------

# download and write the trails data to a geojson file
# source: https://public-nps.opendata.arcgis.com/datasets/nps-trails-web-mercator-1/data?geometry=-91.495%2C32.349%2C-76.674%2C35.538
r = requests.get("https://opendata.arcgis.com/datasets/37ddc6e4c4a045edb5f48c0396e1787b_0.geojson?where=UNITCODE%20%3D%20'chat'")

if r.status_code == 200 and len(str(r.json())) > 1000:
    with open(trails_file, 'w') as f:
        f.write(r.text)
else:
    print('An error occurred downloading trail data: ' + \
          str(r.status_code) + ' (' + r.text + ')' )


# download and write the river data to a geojson file   
# source: https://opendata.atlantaregional.com/datasets/rivers-streams-atlanta-region/data?where=NAME%20%3D%20%27Chattahoochee%20River%27
r = requests.get("https://opendata.arcgis.com/datasets/1d4cb4e279c5485c95e1385769c9b723_28.geojson?where=NAME%20%3D%20%27Chattahoochee%20River%27")

if r.status_code == 200 and len(str(r.json())) > 500:
    with open(river_file, 'w') as f:
        f.write(r.text)
else:
    print('An error occurred downloading river data: ' + \
          str(r.status_code) + ' (' + r.text + ')' )


#-------------------------------------------------------------------------------
# merge the river into a single spatial object
#-------------------------------------------------------------------------------

river = geopandas.read_file(river_file)

# break the MultiLineStrings into a list of LineStrings
split_lines = []
for i in range(len(river)):
    if river['geometry'].iloc[i].geom_type == 'MultiLineString':   
        split_lines += split_multilinestring(river['geometry'].iloc[i])
    else:    # current object is already a Linestring
        split_lines.append(river['geometry'].iloc[i])

river_merged = geopandas.GeoSeries(MultiLineString(split_lines))

river_merged.to_file(river_file_merged, driver='GeoJSON')


#-------------------------------------------------------------------------------
# output a file containing total miles by GEOMETRYID
#-------------------------------------------------------------------------------

data = json.load(open(trails_file, 'r'))

# extract the GEOMETRYID and coordinates from the geoJSON
df = json_normalize(data=data['features'])[['properties.GEOMETRYID','geometry.coordinates']]
df.columns = ['GEOMETRYID', 'coordinates']

# extract the points to rows
df = df.explode('coordinates')

# get the coordinates of the next point
df['next_GEOMETRYID'] = df['GEOMETRYID'].shift(periods=-1)
df['next_coordinates'] = df['coordinates'].shift(periods=-1)
df = df[df['GEOMETRYID'] == df['next_GEOMETRYID']]

# split the lat/lon into columns
df.reset_index(inplace=True)
df[['start_lon', 'start_lat']] = DataFrame(df['coordinates'].tolist())
df[['end_lon', 'end_lat']] = DataFrame(df['next_coordinates'].tolist())

# calculate the length of each segment
df['distance_mi'] = haversine(df['start_lat'].values, df['start_lon'].values,
                              df['end_lat'].values, df['end_lon'].values)

# sum segment lengths by GEOMETRYID
df_sum = df[['GEOMETRYID','distance_mi']].groupby(['GEOMETRYID']).sum()
df_sum.reset_index(inplace=True)

# write the sums to a file
df_sum.to_csv(trails_file_dist, index=False)