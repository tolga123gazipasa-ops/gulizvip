import sys
filepath = "C:/Users/MSI/OneDrive/Desktop/gulizvip/index.html"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Find the function boundaries
old_start = "function initPlaceAutocompleteNew(input, type) {"
old_end = "function initPlaceAutocompleteLegacy(input, type) {"

idx_start = content.find(old_start)
idx_end = content.find(old_end)

if idx_start == -1:
    print("ERROR: Could not find initPlaceAutocompleteNew")
    sys.exit(1)
if idx_end == -1:
    print("ERROR: Could not find initPlaceAutocompleteLegacy")
    sys.exit(1)

print(f"[INFO] initPlaceAutocompleteNew found at position {idx_start}")
print(f"[INFO] initPlaceAutocompleteLegacy found at position {idx_end}")
print(f"[INFO] Function block size: {idx_end - idx_start} chars")

# Extract the old function
old_fn = content[idx_start:idx_end]
print(f"[INFO] Old function starts with: {repr(old_fn[:80])}")

# Build replacement
new_fn = """function initPlaceAutocompleteNew(input, type) {
            // Klasik Autocomplete — web component yazmayı engellediği için bu API kullanılır
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

        """

# Replace
new_content = content[:idx_start] + new_fn + content[idx_end:]

with open(filepath, "w", encoding="utf-8") as f:
    f.write(new_content)

print("[OK] initPlaceAutocompleteNew replaced successfully")
