document.addEventListener("DOMContentLoaded", function () {
    // 1. Theme Management (Light / Dark Mode)
    const themeToggleBtn = document.getElementById("theme-toggle");
    const currentTheme = localStorage.getItem("theme") || "light";

    // Set initial theme
    document.documentElement.setAttribute("data-theme", currentTheme);
    updateThemeIcon(currentTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", function () {
            let theme = document.documentElement.getAttribute("data-theme");
            let newTheme = theme === "dark" ? "light" : "dark";
            
            document.documentElement.setAttribute("data-theme", newTheme);
            localStorage.setItem("theme", newTheme);
            updateThemeIcon(newTheme);
            
            // Dispatch custom event so active charts can re-color if needed
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: newTheme } }));
        });
    }

    function updateThemeIcon(theme) {
        if (!themeToggleBtn) return;
        const icon = themeToggleBtn.querySelector("i");
        if (icon) {
            if (theme === "dark") {
                icon.className = "bi bi-sun-fill text-warning";
            } else {
                icon.className = "bi bi-moon-fill text-secondary";
            }
        }
    }

    // 2. Sidebar Toggle
    const menuToggle = document.getElementById("menu-toggle");
    const wrapper = document.getElementById("wrapper");
    const sidebarOverlay = document.getElementById("sidebar-overlay");
    
    if (menuToggle && wrapper) {
        menuToggle.addEventListener("click", function (e) {
            e.preventDefault();
            wrapper.classList.toggle("toggled");
        });
    }

    if (sidebarOverlay && wrapper) {
        sidebarOverlay.addEventListener("click", function () {
            wrapper.classList.remove("toggled");
        });
    }

    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape" && wrapper && wrapper.classList.contains("toggled")) {
            wrapper.classList.remove("toggled");
        }
    });

    // 3. Global Bootstrap Modal Engine & Lifecycle Hooks
    document.querySelectorAll('.modal-dialog').forEach(function(dialog) {
        if (!dialog.classList.contains('modal-dialog-centered')) {
            dialog.classList.add('modal-dialog-centered');
        }
        if (!dialog.classList.contains('modal-dialog-scrollable')) {
            dialog.classList.add('modal-dialog-scrollable');
        }
    });

    document.body.addEventListener('show.bs.modal', function(event) {
        const modal = event.target;
        modal.querySelectorAll('.alert-danger, .alert-warning').forEach(alert => {
            if (!alert.classList.contains('persistent-alert')) {
                alert.classList.add('d-none');
                alert.textContent = '';
            }
        });
    });

    document.body.addEventListener('shown.bs.modal', function(event) {
        const modal = event.target;
        const firstInput = modal.querySelector('input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])');
        if (firstInput) {
            firstInput.focus();
        }
    });

    document.body.addEventListener('hidden.bs.modal', function(event) {
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';

        if (document.querySelectorAll('.modal.show').length === 0) {
            document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
        }
    });

    // 4. Mark Notifications as Read
    const notificationDropdownBtn = document.getElementById("navbarDropdownNotifications");
    if (notificationDropdownBtn) {
        notificationDropdownBtn.addEventListener("click", function () {
            // Send an AJAX request to mark all notifications as read
            fetch('/notifications/mark-read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const badge = document.querySelector("#navbarDropdownNotifications .badge");
                    if (badge) {
                        badge.remove(); // Remove count badge
                    }
                }
            })
            .catch(err => console.error("Error marking notifications read:", err));
        });
    }

    // Helper to extract CSRF token from forms if exists
    function getCsrfToken() {
        const tokenInput = document.querySelector('input[name="csrf_token"]');
        return tokenInput ? tokenInput.value : '';
    }
});

// 4. Chart.js Helper Functions
window.NGOCharts = {
    colors: {
        teal: '#0d9488',
        indigo: '#6366f1',
        amber: '#f59e0b',
        rose: '#ef4444',
        emerald: '#10b981',
        slate: '#64748b'
    },
    
    createLineChart: function (canvasId, labels, data, labelName) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: labelName,
                    data: data,
                    borderColor: this.colors.teal,
                    backgroundColor: 'rgba(13, 148, 136, 0.1)',
                    tension: 0.3,
                    fill: true,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0, 0, 0, 0.05)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },

    createBarChart: function (canvasId, labels, data, labelName, colorName = 'indigo') {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        const barColor = this.colors[colorName] || this.colors.indigo;
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: labelName,
                    data: data,
                    backgroundColor: barColor,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0, 0, 0, 0.05)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },

    createDoughnutChart: function (canvasId, labels, data) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        return new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        this.colors.teal,
                        this.colors.indigo,
                        this.colors.amber,
                        this.colors.rose,
                        this.colors.slate
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 12, padding: 15 }
                    }
                }
            }
        });
    }
};

// 5. QR Code Scanner Handler
window.initQRScanner = function(scanSuccessCallback) {
    const qrReaderEl = document.getElementById("qr-reader");
    if (!qrReaderEl) return;
    
    // Check if Html5QrcodeScanner is loaded from CDN
    if (typeof Html5QrcodeScanner !== "undefined") {
        let html5QrcodeScanner = new Html5QrcodeScanner(
            "qr-reader", 
            { fps: 10, qrbox: { width: 250, height: 250 } },
            /* verbose= */ false
        );
        html5QrcodeScanner.render(scanSuccessCallback, (errorMessage) => {
            // Keep scan silent unless debug needed
            // console.warn(`QR scan error: ${errorMessage}`);
        });
        return html5QrcodeScanner;
    } else {
        console.error("Html5QrcodeScanner script not loaded.");
        qrReaderEl.innerHTML = "<p class='text-danger p-3'>QR Library failed to load. Use the manual scan option.</p>";
        return null;
    }
};
