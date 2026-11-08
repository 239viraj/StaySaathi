function getFindPGLocation() {

    const status =
        document.getElementById("find-location-status");

    const button =
        document.getElementById("find-location-button");

    if (!navigator.geolocation) {

        status.innerText =
            "❌ Your browser does not support location detection.";

        return;
    }

    status.innerText =
        "📍 Detecting your location...";

    button.disabled = true;

    button.innerText =
        "Detecting Location...";


    navigator.geolocation.getCurrentPosition(

        function(position) {

            const latitude =
                position.coords.latitude;

            const longitude =
                position.coords.longitude;


            console.log("User Latitude:", latitude);
            console.log("User Longitude:", longitude);


            // =========================
            // SAVE LOCATION
            // =========================

            document.getElementById(
                "search-latitude"
            ).value = latitude;


            document.getElementById(
                "search-longitude"
            ).value = longitude;


            // =========================
            // SELECT NEAREST FIRST
            // =========================

            const sortSelect =
                document.getElementById("sort_by");

            if (sortSelect) {

                sortSelect.value = "nearest";

            }


            status.innerText =
                "✓ Location captured. Finding nearest PGs...";

            button.innerText =
                "✓ Location Captured";


            // =========================
            // SUBMIT SEARCH FORM
            // =========================

            const searchForm =
                document.querySelector(".pg-search-form");

            if (searchForm) {

                searchForm.submit();

            }

        },


        function(error) {

            button.disabled = false;

            button.innerText =
                "📍 Use My Location";


            if (error.code === 1) {

                status.innerText =
                    "❌ Location permission was denied.";

            }

            else if (error.code === 2) {

                status.innerText =
                    "❌ Location is unavailable.";

            }

            else if (error.code === 3) {

                status.innerText =
                    "❌ Location request timed out.";

            }

            else {

                status.innerText =
                    "❌ Unable to detect your location.";

            }

        },


        {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
        }

    );
}

/* =========================================
   PG COMPARISON
========================================= */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const checkboxes =
            document.querySelectorAll(
                ".compare-pg-checkbox"
            );

        const compareBar =
            document.getElementById(
                "compare-bar"
            );

        const compareCount =
            document.getElementById(
                "compare-count"
            );

        const compareButton =
            document.getElementById(
                "compare-now-btn"
            );

        const clearButton =
            document.getElementById(
                "clear-compare-btn"
            );


        if (!checkboxes.length) {
            return;
        }


        let selectedPGs = [];


        /* =========================
           UPDATE COMPARE BAR
        ========================== */

        function updateCompareBar() {

            const count =
                selectedPGs.length;


            if (count > 0) {

                compareBar.classList.add(
                    "show"
                );

            } else {

                compareBar.classList.remove(
                    "show"
                );

            }


            if (count === 1) {

                compareCount.innerText =
                    "1 PG selected";

            } else {

                compareCount.innerText =
                    count + " PGs selected";

            }


            /*
             * At least 2 PGs are required
             * for comparison.
             */

            compareButton.disabled =
                count < 2;


            /*
             * Maximum 3 PGs.
             */

            checkboxes.forEach(
                function (checkbox) {

                    if (
                        !checkbox.checked &&
                        count >= 3
                    ) {

                        checkbox.disabled = true;

                    } else {

                        checkbox.disabled = false;

                    }

                }
            );

        }


        /* =========================
           CHECKBOX CHANGE
        ========================== */

        checkboxes.forEach(
            function (checkbox) {

                checkbox.addEventListener(
                    "change",
                    function () {

                        const pgId =
                            this.value;


                        if (this.checked) {

                            if (
                                selectedPGs.length >= 3
                            ) {

                                this.checked =
                                    false;

                                alert(
                                    "You can compare a maximum of 3 PGs."
                                );

                                return;
                            }


                            selectedPGs.push(
                                pgId
                            );

                        } else {

                            selectedPGs =
                                selectedPGs.filter(
                                    function (id) {

                                        return id !== pgId;

                                    }
                                );

                        }


                        updateCompareBar();

                    }
                );

            }
        );


        /* =========================
           CLEAR
        ========================== */

        clearButton.addEventListener(
            "click",
            function () {

                selectedPGs = [];


                checkboxes.forEach(
                    function (checkbox) {

                        checkbox.checked =
                            false;

                        checkbox.disabled =
                            false;

                    }
                );


                updateCompareBar();

            }
        );


        /* =========================
           COMPARE NOW
        ========================== */

        compareButton.addEventListener(
            "click",
            function () {

                if (
                    selectedPGs.length < 2
                ) {

                    alert(
                        "Please select at least 2 PGs to compare."
                    );

                    return;

                }


                const ids =
                    selectedPGs.join(",");


                window.location.href =
                    "/compare-pgs?ids="
                    + encodeURIComponent(ids);

            }
        );


        updateCompareBar();

    }
);

/* =========================================
   GET DIRECTIONS
========================================= */

function getDirections(
    pgLatitude,
    pgLongitude
) {

    // Check browser support
    if (!navigator.geolocation) {

        alert(
            "Your browser does not support location detection."
        );

        return;
    }


    // Show a small message while getting location
    const originalTitle =
        document.title;

    document.title =
        "Getting your location...";


    navigator.geolocation.getCurrentPosition(

        function (position) {

            // Restore title
            document.title =
                originalTitle;


            const userLatitude =
                position.coords.latitude;

            const userLongitude =
                position.coords.longitude;


            // =========================
            // GOOGLE MAPS DIRECTIONS
            // =========================

            const directionsURL =
                "https://www.google.com/maps/dir/?api=1"
                + "&origin="
                + encodeURIComponent(
                    userLatitude
                    + ","
                    + userLongitude
                )
                + "&destination="
                + encodeURIComponent(
                    pgLatitude
                    + ","
                    + pgLongitude
                );


            // Open Google Maps
            window.open(
                directionsURL,
                "_blank"
            );

        },


        function (error) {

            // Restore title
            document.title =
                originalTitle;


            if (error.code === 1) {

                alert(
                    "Location permission was denied. " +
                    "Please allow location access to get directions."
                );

            }

            else if (error.code === 2) {

                alert(
                    "Your location could not be determined. " +
                    "Please check your device location settings."
                );

            }

            else if (error.code === 3) {

                alert(
                    "Location request timed out. " +
                    "Please try again."
                );

            }

            else {

                alert(
                    "Unable to get your location. " +
                    "Please try again."
                );

            }

        },


        {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
        }

    );

}
/* =========================================
   DIRECTIONS BUTTON CLICK HANDLER
========================================= */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const directionButtons =
            document.querySelectorAll(
                ".directions-button"
            );


        directionButtons.forEach(
            function (button) {

                button.addEventListener(
                    "click",
                    function () {

                        const latitude =
                            parseFloat(
                                this.dataset.latitude
                            );

                        const longitude =
                            parseFloat(
                                this.dataset.longitude
                            );


                        if (
                            Number.isNaN(latitude) ||
                            Number.isNaN(longitude)
                        ) {

                            alert(
                                "PG location is not available."
                            );

                            return;
                        }


                        getDirections(
                            latitude,
                            longitude
                        );

                    }
                );

            }
        );

    }
);