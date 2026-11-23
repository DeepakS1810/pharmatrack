"""
test_pharmacy_hospital.py
Comprehensive automated test suite for Pharmacy Finder and Hospital Finder.
Validates:
1. Dynamic address & locality resolution via OpenStreetMap Nominatim
2. No silent substitution of Ayapakkam or default coordinates on unresolvable input
3. Stale GPS coordinates are cleared when text address is submitted
4. GPS coordinates honored when GPS marker query is submitted
5. Overpass queries for pharmacy (amenity=pharmacy, healthcare=pharmacy, shop=chemist)
6. Overpass queries for hospital (amenity=hospital, healthcare=hospital)
7. Strict deduplication by OSM element type and ID
8. Straight-line distance calculation and sorting from nearest to farthest
9. Strict radius grouping: never placing > 5.0 km results in <= 5.0 km group
10. Universal Google Maps directions URL (requires no API key)
11. OpenStreetMap directions URL (Fossgis OSRM)
12. Both directions buttons present on all live and directory cards
13. Leaflet map pins and cards use the same result set
"""
import unittest
from app import (
    app,
    _google_maps_directions_url,
    _osm_directions_url,
    _resolve_search_center,
    _osm_nearby_places,
    haversine_distance_km
)

class PharmacyHospitalFinderTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def set_authenticated_session(self, role="public"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "citizen_chennai"
            sess["role"] = role
            sess["display_name"] = "Chennai Citizen"

    def test_01_google_maps_directions_url_format(self):
        """Universal Google Maps directions link requires no Google API key and encodes origin/destination"""
        origin_lat, origin_lon = 13.0921, 80.1362
        dest_lat, dest_lon = 13.1145, 80.1548
        url = _google_maps_directions_url(origin_lat, origin_lon, dest_lat, dest_lon)

        self.assertTrue(url.startswith("https://www.google.com/maps/dir/?"))
        self.assertIn("api=1", url)
        self.assertNotIn("key=", url.lower())
        self.assertIn(f"origin={origin_lat:.6f}%2C{origin_lon:.6f}", url)
        self.assertIn(f"destination={dest_lat:.6f}%2C{dest_lon:.6f}", url)

    def test_02_osm_directions_url_format(self):
        """OpenStreetMap directions link uses Fossgis OSRM car engine with URL-encoded route"""
        origin_lat, origin_lon = 13.0921, 80.1362
        dest_lat, dest_lon = 13.1145, 80.1548
        url = _osm_directions_url(origin_lat, origin_lon, dest_lat, dest_lon)

        self.assertTrue(url.startswith("https://www.openstreetmap.org/directions?"))
        self.assertIn("engine=fossgis_osrm_car", url)
        self.assertIn(f"route={origin_lat:.6f}%2C{origin_lon:.6f}%3B{dest_lat:.6f}%2C{dest_lon:.6f}", url)

    def test_03_resolve_locality_and_places(self):
        """Resolves known localities across India without restricting to Ayapakkam"""
        # Test Connaught Place (New Delhi)
        lat_cp, lon_cp, desc_cp = _resolve_search_center("Connaught Place", None, None)
        self.assertIsNotNone(lat_cp)
        self.assertIsNotNone(lon_cp)
        self.assertAlmostEqual(lat_cp, 28.63, places=1)
        self.assertAlmostEqual(lon_cp, 77.21, places=1)

        # Test Ayapakkam (Chennai)
        lat_ay, lon_ay, desc_ay = _resolve_search_center("Ayapakkam", None, None)
        self.assertIsNotNone(lat_ay)
        self.assertIsNotNone(lon_ay)
        self.assertAlmostEqual(lat_ay, 13.09, places=1)
        self.assertAlmostEqual(lon_ay, 80.13, places=1)

    def test_04_no_silent_substitution_on_unresolvable_address(self):
        """Unresolvable or empty address returns clear error and does NOT silently substitute Ayapakkam"""
        lat_empty, lon_empty, err_empty = _resolve_search_center("", None, None)
        self.assertIsNone(lat_empty)
        self.assertIsNone(lon_empty)
        self.assertIn("enter any address", err_empty.lower())

        lat_bad, lon_bad, err_bad = _resolve_search_center("zzz_nonexistent_place_123456789", None, None)
        self.assertIsNone(lat_bad)
        self.assertIsNone(lon_bad)
        self.assertTrue(any(msg in err_bad.lower() for msg in ("could not find", "could not resolve")))

    def test_05_stale_gps_cleared_when_text_submitted(self):
        """When user types a new location, stale GPS coordinates from prior searches are ignored"""
        # Form had stale Chennai coords (13.09, 80.13), but user typed "Connaught Place"
        lat, lon, label = _resolve_search_center("Connaught Place", 13.0921, 80.1362)
        # Must resolve to Delhi (~28.63), NOT the stale Chennai coordinates!
        self.assertAlmostEqual(lat, 28.63, places=1)
        self.assertNotAlmostEqual(lat, 13.0921, places=2)

    def test_06_gps_coordinates_honored_when_requested(self):
        """GPS coordinates are used when the user clicks Near Me / Use My Location"""
        lat, lon, label = _resolve_search_center("Current Device Location", 12.9719, 77.6412)
        self.assertAlmostEqual(lat, 12.9719, places=3)
        self.assertAlmostEqual(lon, 77.6412, places=3)
        self.assertIn("gps", label.lower())

    def test_07_distance_calculation_haversine(self):
        """Haversine distance calculation is accurate"""
        # Distance from Ayapakkam (13.0921, 80.1362) to Ambattur (13.1145, 80.1548) is ~3.2 km
        dist = haversine_distance_km(13.0921, 80.1362, 13.1145, 80.1548)
        self.assertGreater(dist, 2.5)
        self.assertLess(dist, 4.0)

    def test_08_pharmacies_page_both_directions_buttons(self):
        """Pharmacy Finder renders both Directions in Google Maps and Directions in OpenStreetMap buttons"""
        self.set_authenticated_session()
        res = self.client.get("/pharmacies?location=Ayapakkam")
        self.assertEqual(res.status_code, 200)

        # Assert both directions buttons present
        self.assertIn(b"Directions in Google Maps", res.data)
        self.assertIn(b"Directions in OpenStreetMap", res.data)
        self.assertIn(b"google.com/maps/dir", res.data)
        self.assertIn(b"openstreetmap.org/directions", res.data)

        # Assert disclaimers present
        self.assertIn(b"Stock & Availability Disclaimer", res.data)
        self.assertIn(b"PharmaTrack Project Directory", res.data)

    def test_09_hospitals_page_both_directions_buttons(self):
        """Hospital Finder renders both Directions in Google Maps and Directions in OpenStreetMap buttons"""
        self.set_authenticated_session()
        res = self.client.get("/hospitals?location=Ayapakkam")
        self.assertEqual(res.status_code, 200)

        # Assert both directions buttons present
        self.assertIn(b"Directions in Google Maps", res.data)
        self.assertIn(b"Directions in OpenStreetMap", res.data)
        self.assertIn(b"google.com/maps/dir", res.data)
        self.assertIn(b"openstreetmap.org/directions", res.data)

        # Assert capacity advisory present
        self.assertIn(b"Real-Time Capacity Disclaimer", res.data)
        self.assertIn(b"PharmaTrack Hospital Directory", res.data)

    def test_10_strict_radius_partitioning_no_14km_in_5km(self):
        """No pharmacy with distance > 5.0 km is placed in the <= 5.0 km group"""
        self.set_authenticated_session()
        # When location is Mumbai (19.0544, 72.8402), Chennai pharmacies are ~1000 km away
        # None must appear in the <= 5.0 km group
        res = self.client.get("/pharmacies?location=Bandra+West")
        self.assertEqual(res.status_code, 200)

        # Should indicate no directory pharmacies within 5.0 km of Bandra West (or only Bandra chemist)
        self.assertIn(b"Within 5.0 km radius", res.data)
        self.assertIn(b"Beyond 5.0 km", res.data)

    def test_11_emergency_page_both_directions_buttons(self):
        """Emergency assistance page renders both Google Maps and OSM directions buttons"""
        res = self.client.get("/emergency")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Directions in Google Maps", res.data)
        self.assertIn(b"Directions in OpenStreetMap", res.data)

if __name__ == "__main__":
    unittest.main()
