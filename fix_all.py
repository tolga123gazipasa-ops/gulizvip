"""
Comprehensive fix for index.html:
1. Replace initPlacesAutocomplete() - use classic API only
2. Replace initPlaceAutocompleteNew() with classic Autocomplete
3. Add predefined pickup coordinates (GZP, AYT, Alanya)
4. Add showRouteMap() to legacy function fallback
5. Fix pickup select to trigger map on change
"""
import sys

filepath = "/sessions/tender-wizardly-edison/mnt/gulizvip/index.html"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# ----- 1. Replace initPlacesAutocomplete() -----
old_dispatch = """        function initPlacesAutocomplete() {
            // Transfer form — varış noktası (PlaceAutocompleteElement)
            var destInput = document.getElementById('dest-input');
            if(destInput && window.google && google.maps && google.maps.places) {
                // PlaceAutocompleteElement kullan (2025 sonrası yeni API)
                if(google.maps.places.PlaceAutocompleteElement) {
                    initPlaceAutocompleteNew(destInput, 'dest');
                } else {
                    // Fallback: eski Autocomplete
                    initPlaceAutocompleteLegacy(destInput, 'dest');
                }
            }

            // Tahsis formu — alış noktası
            var tahsisInput = document.getElementById('tahsis-pickup-input');
            if(tahsisInput && window.google && google.maps && google.maps.places) {
                if(google.maps.places.PlaceAutocompleteElement) {
                    initPlaceAutocompleteNew(tahsisInput, 'tahsis');
                } else {
                    initPlaceAutocompleteLegacy(tahsisInput, 'tahsis');
                }
            }
        }"""

new_dispatch = """        function initPlacesAutocomplete() {
            // Transfer form — varış noktası (klasik Autocomplete, shadow DOM sorunu yok)
            var destInput = document.getElementById('dest-input');
            if(destInput && window.google && google.maps && google.maps.places) {
                initPlaceAutocompleteClassic(destInput, 'dest');
            }

            // Tahsis formu — alış noktası
            var tahsisInput = document.getElementById('tahsis-pickup-input');
            if(tahsisInput && window.google && google.maps && google.maps.places) {
                initPlaceAutocompleteClassic(tahsisInput, 'tahsis');
            }
        }"""

if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch)
    print("[OK] initPlacesAutocomplete replaced")
else:
    print("[ERR] initPlacesAutocomplete not found")
    # Debug: find approximate location
    idx = content.find("function initPlacesAutocomplete")
    print(f"  Found at index {idx}")
    if idx >= 0:
        print(f"  Next 100 chars: {repr(content[idx:idx+100])}")

# ----- 2. Replace initPlaceAutocompleteNew() -----
old_new_fn_start = "        function initPlaceAutocompleteNew(input, type) {"
old_new_fn_end = "        function initPlaceAutocompleteLegacy(input, type) {"

idx_start = content.find(old_new_fn_start)
idx_end = content.find(old_new_fn_end)

if idx_start >= 0 and idx_end >= 0:
    new_fn = """        function initPlaceAutocompleteClassic(input, type) {
            // Klasik Autocomplete — shadow DOM yok, input yazılabilir, öneriler düzgün çalışır
            var autocomplete = new google.maps.places.Autocomplete(input, {
                types: ['geocode', 'establishment'],
                componentRestrictions: { country: 'TR' },
                fields: ['formatted_address', 'geometry', 'location', 'name', 'place_id']
            });

            autocomplete.addListener('place_changed', function() {
                var place = autocomplete.getPlace();
                if(!place || !place.geometry || !place.geometry.location) {
                    return;
                }

                var lat = place.geometry.location.lat();
                var lng = place.geometry.location.lng();

                if(type === 'dest') {
                    selectedDestLat = lat;
                    selectedDestLng = lng;
                    showRouteMap();
                    calculateTransferDistance();
                } else {
                    selectedPickupLat = lat;
                    selectedPickupLng = lng;
                }
            });
        }

        function initPlaceAutocompleteLegacy(input, type) {"""
    content = content[:idx_start] + new_fn + content[idx_end:]
    print("[OK] initPlaceAutocompleteNew -> initPlaceAutocompleteClassic replaced")
else:
    print(f"[ERR] Could not find boundaries: start={idx_start}, end={idx_end}")

# ----- 3. Add predefined pickup coordinates + map trigger -----
# After the DOMContentLoaded pickup select listener (line ~1165), we need to add
# a richer handler that sets coordinates and shows the map when pickup changes.

old_pickup_handler = """        // Trigger distance calc when pickup select changes
        document.addEventListener('DOMContentLoaded', function() {
            var select = document.querySelector('#form-transfer select:first-child');
            if(select) {
                select.addEventListener('change', function() {
                    calculateTransferDistance();
                });
            }
        });"""

new_pickup_handler = """        // Pickup select — koordinatları ata ve haritayı hemen göster
        // Öntanımlı noktalar: Gazipaşa Havalimanı, Antalya Havalimanı, Alanya
        var PICKUP_COORDS = {
            'Gazipaşa Havalimanı (GZP)': { lat: 36.2992, lng: 32.3014 },
            'Antalya Havalimanı (AYT)':   { lat: 36.9019, lng: 30.7917 },
            'Alanya Merkez / Otel':       { lat: 36.5467, lng: 32.0017 }
        };

        document.addEventListener('DOMContentLoaded', function() {
            var select = document.querySelector('#form-transfer select:first-child');
            if(select) {
                // Initial pickup coords
                var initial = PICKUP_COORDS[select.value];
                if(initial) {
                    selectedPickupLat = initial.lat;
                    selectedPickupLng = initial.lng;
                }

                select.addEventListener('change', function() {
                    var coords = PICKUP_COORDS[select.value];
                    if(coords) {
                        selectedPickupLat = coords.lat;
                        selectedPickupLng = coords.lng;
                    }
                    calculateTransferDistance();
                    // Harita zaten açık değilse ve varış seçilmişse göster
                    var destVal = document.getElementById('dest-input').value.trim();
                    if(destVal.length >= 3 || (selectedDestLat && selectedDestLng)) {
                        showRouteMap();
                    }
                });
            }
        });"""

if old_pickup_handler in content:
    content = content.replace(old_pickup_handler, new_pickup_handler)
    print("[OK] Pickup select handler replaced with coordinates + map trigger")
else:
    print("[ERR] Old pickup handler not found")
    idx = content.find("Trigger distance calc when pickup")
    if idx >= 0:
        print(f"  Found at {idx}: {repr(content[idx:idx+120])}")

# ----- 4. Update showRouteMap() to use pickup coordinates if available -----
old_origin = """            var directionsService = new google.maps.DirectionsService();
            var pickupSelect = document.querySelector('#form-transfer select:first-child');
            var pickupText = pickupSelect ? pickupSelect.value : 'Gazipaşa Havalimanı (GZP)';
            var originStr = pickupText.replace(' (GZP)', ', Gazipaşa').replace(' (AYT)', ', Antalya');
            var destStr = document.getElementById('dest-input').value;

            if(selectedDestLat && selectedDestLng) {
                destStr = selectedDestLat + ',' + selectedDestLng;
            }

            directionsService.route({
                origin: originStr,"""

new_origin = """            var directionsService = new google.maps.DirectionsService();
            var destStr = document.getElementById('dest-input').value;
            var originStr = '';

            // Seçili pickup koordinatı varsa onu kullan, yoksa select text'ten dene
            if(selectedPickupLat && selectedPickupLng) {
                originStr = selectedPickupLat + ',' + selectedPickupLng;
            } else {
                var pickupSelect = document.querySelector('#form-transfer select:first-child');
                var pickupText = pickupSelect ? pickupSelect.value : 'Gazipaşa Havalimanı (GZP)';
                originStr = pickupText.replace(' (GZP)', ', Gazipaşa').replace(' (AYT)', ', Antalya');
            }

            if(selectedDestLat && selectedDestLng) {
                destStr = selectedDestLat + ',' + selectedDestLng;
            }

            directionsService.route({
                origin: originStr,"""

if old_origin in content:
    content = content.replace(old_origin, new_origin)
    print("[OK] showRouteMap() updated with pickup coordinates")
else:
    print("[ERR] showRouteMap origin block not found")
    idx = content.find("var directionsService = new google.maps.DirectionsService()")
    if idx >= 0:
        print(f"  Found at {idx}: {repr(content[idx:idx+200])}")

# ----- 5. Add pickup coords to initPlaceAutocompleteLegacy -----
old_legacy_handler = """            ac.addListener('place_changed', function() {
                var place = ac.getPlace();
                if(place.geometry) {
                    var lat = place.geometry.location.lat();
                    var lng = place.geometry.location.lng();
                    if(type === 'dest') {
                        selectedDestLat = lat;
                        selectedDestLng = lng;
                        calculateTransferDistance();
                    } else {
                        selectedPickupLat = lat;
                        selectedPickupLng = lng;
                    }
                }
            });"""

new_legacy_handler = """            ac.addListener('place_changed', function() {
                var place = ac.getPlace();
                if(place && place.geometry && place.geometry.location) {
                    var lat = place.geometry.location.lat();
                    var lng = place.geometry.location.lng();
                    if(type === 'dest') {
                        selectedDestLat = lat;
                        selectedDestLng = lng;
                        showRouteMap();
                        calculateTransferDistance();
                    } else {
                        selectedPickupLat = lat;
                        selectedPickupLng = lng;
                    }
                }
            });"""

if old_legacy_handler in content:
    content = content.replace(old_legacy_handler, new_legacy_handler)
    print("[OK] initPlaceAutocompleteLegacy updated with showRouteMap()")
else:
    print("[ERR] Legacy handler not found (may already be updated)")

# ----- 6. Revert the tahsis-pickup-input to not use PlaceAutocompleteElement -----
# The tahsis-pickup-input already uses initPlaceAutocompleteClassic now since
# we replaced the dispatcher. Good.

# ----- Write result -----
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("\n[DONE] All fixes applied. File written successfully.")
