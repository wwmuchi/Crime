import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import folium_static 
import ast
import geopandas as gpd
from branca.element import Element
import statsmodels.api as sm



# Import
if "tot_crime_rate" not in st.session_state:
    with st.spinner("Loading crime data..."):
        try:
            csv_url = "https://www.dropbox.com/scl/fi/qrf6mh78lxhl7blojw8jq/TotCrimeRateAndControls.csv?rlkey=j745h7o6pbjdzgzg618iopqav&dl=1"
            st.session_state.tot_crime_rate = pd.read_csv(csv_url)
        except Exception as e:
            st.error(f"Failed to load crime data: {e}")
        else:
            st.success("Crime data loaded successfully!", icon="✅")

if "gdf" not in st.session_state:
    with st.spinner("Loading radio station data..."):
        try:
            geojson_url = "https://www.dropbox.com/scl/fi/d9l3t5bv7vt8uvyrdiocr/RadioData.geojson?rlkey=l38owj7hkbx06vvlend8sevkc&dl=1"
            st.session_state.gdf = gpd.read_file(geojson_url)
        except Exception as e:
            st.error(f"Failed to load radio station data: {e}")
        else:
            st.success("Radio station data loaded successfully!", icon="✅")

# Data pre-processing
tot_crime_rate = st.session_state.tot_crime_rate.copy()
gdf = st.session_state.gdf.copy()

tot_crime_rate.drop(columns=['state_fips', 'county_fips', 'county_level', 'state_level'], inplace=True)

# Title
st.title("Crime Rate and Hip Hop Coverage Map")

# Year selection
years_in_data = set.intersection(set(gdf['year']), set(tot_crime_rate['year']))
year = st.slider("Select Year", min_value=min(years_in_data), max_value=max(years_in_data), value=max(years_in_data))


# Identify columns
columns = tot_crime_rate.columns
indices = [i for i, col in enumerate(columns) if "(\'" in col]
first_index = indices[0]
last_index = indices[-1]
crime_cols = tot_crime_rate.columns[first_index:last_index+1]
control_cols_all = tot_crime_rate.columns[last_index+1:]

# Crime type selection
def parse_tuple(s):
    s = s.strip("()")  # Remove parentheses
    return tuple(item.strip().strip("'\"") for item in s.split(","))

crime_types = pd.Series(crime_cols).apply(parse_tuple)
crimes = crime_types.apply(lambda x: x[1]).drop_duplicates()
types = crime_types.apply(lambda x: x[0]).drop_duplicates()


crime_mapping = {c.replace('_', ' ').title(): c for c in crimes}
display_crimes = list(crime_mapping.keys())
crime_selection_display = st.selectbox("Select Crime", display_crimes, index=0)

type_mapping = {t.replace('_', ' ').title(): t for t in types}
display_types = list(type_mapping.keys())
type_selection_display = st.selectbox("Select Crime Type", display_types, index=0)

# Control selection
control_cols = st.multiselect("Select Controls", control_cols_all)

# Data type selection
data_type = 'Concentration'

type_map = {'Binary': 'binar', 'Concentration': 'conc', 'Concentration & Rating': 'rat'}

if data_type in type_map:
    gdf.drop(columns=[col for col in gdf.columns if 'HH' in col and type_map[data_type] not in col], inplace=True)
    gdf.columns = gdf.columns.str.replace(f"_{type_map[data_type]}", '')


gdf.dropna(inplace=True)


# Mapping
if "map_rendered" not in st.session_state:
    st.session_state["map_rendered"] = False
if "map" not in st.session_state:
    st.session_state["map"] = None

def generate_map(gdf, tot_crime_rate):

    st.session_state['year'] = year
    st.session_state['type_selection_display'] = type_selection_display
    st.session_state['crime_selection_display'] = crime_selection_display
    st.session_state['data_type'] = data_type
    st.session_state['control_cols'] = control_cols


    # Filter data
    filtered_gdf = gdf[gdf['year'] == year]
    filtered_gdf.drop(columns=['year'], inplace=True)
    tot_crime_rate = tot_crime_rate[tot_crime_rate['year'] == year]

    # Get crime type string

    type_selection_internal = type_mapping[type_selection_display]
    crime_selection_internal = crime_mapping[crime_selection_display]

    crime_type = crime_types[
        (crime_types.apply(lambda x: x[1]) == crime_selection_internal) &
        (crime_types.apply(lambda x: x[0]) == type_selection_internal)
    ].values[0]

    crime_type = str(crime_type)

    # Add controls
    X = tot_crime_rate[control_cols]
    y = tot_crime_rate[crime_type]

    X = sm.add_constant(X)

    model = sm.OLS(y, X).fit()

    residuals = model.resid

    normalized_residuals = (residuals - residuals.mean()) / residuals.std()

    tot_crime_rate[crime_type] = normalized_residuals

    # Filter out controls
    tot_crime_rate = tot_crime_rate[['lat', 'long', crime_type]]


    # Create a folium map
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=3, control=False)

    # Create a FeatureGroup for radio stations
    radio_station_group = folium.FeatureGroup(name="Radio Station", overlay=True, show=True)

    # Subset for blue polygons (non-HH)
    filtered_gdf_non_HH = filtered_gdf[filtered_gdf["HH"] < 1]
    for _, row in filtered_gdf_non_HH.iterrows():
        val_non_HH = 1 - row["HH"]

        def style_function_blue(feature):
            return {
                "fillColor": f"rgba(0, 0, 255, {val_non_HH:.2f})",
                "color": "black",
                "weight": 0.1,
                "fillOpacity": val_non_HH,
            }

        folium.GeoJson(
            row["geometry"],
            style_function=style_function_blue,
            tooltip=f"Station: {row['letters']} - {row['broadcast']}, Non-Hip Hop Score: {val_non_HH:.2f}"
        ).add_to(radio_station_group)

    # Subset for red polygons (HH)
    filtered_gdf_HH = filtered_gdf[filtered_gdf["HH"] > 0]
    for _, row in filtered_gdf_HH.iterrows():
        val_HH = row["HH"]

        def style_function_red(feature):
            return {
                "fillColor": f"rgba(255, 0, 0, {val_HH:.2f})",
                "color": "black",
                "weight": 0.1,
                "fillOpacity": val_HH,
            }

        folium.GeoJson(
            row["geometry"],
            style_function=style_function_red,
            tooltip=f"Station: {row['letters']} - {row['broadcast']}, Hip Hop Score: {val_HH:.2f}"
        ).add_to(radio_station_group)

    # Add the radio station group to the map
    radio_station_group.add_to(m)
    
    heatmap_group = folium.FeatureGroup(name=f"Crime Rate ({crime_selection_display}, {type_selection_display})", overlay=True, show=False)

    heatmap_points = tot_crime_rate.values.tolist()

    # Create the HeatMap layer and add it to the heatmap group
    HeatMap(
        heatmap_points,
        min_opacity=0.3,
        radius=10,
        blur=4,
        max_zoom=1000
    ).add_to(heatmap_group)

    # Add the HeatMap group to the map
    heatmap_group.add_to(m)

    # Add a layer control to the map
    folium.LayerControl(collapsed=False).add_to(m)

    return m

if st.button("Load Map"):
    m = generate_map(gdf, tot_crime_rate)
    folium_static(m, width=700, height=500)

    radio_legend_html = '''
    <div style="
        width: 100%;
        background-color: white;
        border: 2px solid black;
        padding: 10px;
        font-size: 14px;
        line-height: 1.5;
        text-align: left;
        margin-bottom: 5mm;
    ">
        <b>Radio Station Legend</b><br>
        <i style="background: rgba(0, 0, 255, 1); width: 20px; height: 10px; display: inline-block;"></i> Station Plays No Hip Hop (Blue)<br>
        <i style="background: rgba(255, 0, 0, 1); width: 20px; height: 10px; display: inline-block;"></i> Station Only Plays Hip Hop (Red)<br>
        <i style="background: rgba(0, 0, 255, 0.66); width: 20px; height: 10px; display: inline-block;"></i> Station Plays Mostly Non-Hip Hop (Transparent Blue)<br>
        <i style="background: rgba(255, 0, 0, 0.66); width: 20px; height: 10px; display: inline-block;"></i> Station Plays Mostly Hip Hop (Transparent Red)<br>
    </div>
    '''

    heatmap_legend_html = '''
    <div style="
        width: 100%;
        background-color: white;
        border: 2px solid black;
        padding: 10px;
        font-size: 14px;
        line-height: 1.5;
        text-align: left;
    ">
        <b>Crime Rate Legend</b><br>
        <i style="background: rgba(0, 0, 255, 1); width: 20px; height: 10px; display: inline-block;"></i> Lowest Crime (Blue)<br>
        <i style="background: rgba(128, 0, 128, 1); width: 20px; height: 10px; display: inline-block;"></i> Low-Medium Crime (Purple)<br>
        <i style="background: rgba(0, 255, 0, 1); width: 20px; height: 10px; display: inline-block;"></i> Medium Crime (Green)<br>
        <i style="background: rgba(255, 165, 0, 1); width: 20px; height: 10px; display: inline-block;"></i> High Crime (Yellow/Orange)<br>
        <i style="background: rgba(255, 0, 0, 1); width: 20px; height: 10px; display: inline-block;"></i> Highest Crime (Red)<br>
    </div>


    '''

    st.markdown(radio_legend_html, unsafe_allow_html=True)
    st.markdown(heatmap_legend_html, unsafe_allow_html=True)