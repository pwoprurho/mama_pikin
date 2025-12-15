document.addEventListener('DOMContentLoaded', function() {
    // --- Safe Initialization ---
    if (document.getElementById('agentCallsChart')) initializeDashboard();
    if (document.getElementById('send-button')) setupChatbot();
    if (document.getElementById('kpi-patients-registered')) initializePublicKpis();
    if (document.getElementById('notesModal')) setupVolunteerQueueModal();
    if (document.getElementById('state')) setupLocationDropdowns();
    if (document.getElementById('state-filter')) setupSupaUserLocationFilter();

    // --- SIDEBAR TOGGLE ---
    if (document.getElementById('menu-toggle')) {
        const menuToggle = document.getElementById('menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay'); // If you have one
        
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('active');
        });
        
        // Close sidebar when clicking outside (optional safety)
        document.addEventListener('click', (e) => {
             if (window.innerWidth <= 992 && sidebar.classList.contains('active') && !sidebar.contains(e.target) && e.target !== menuToggle) {
                sidebar.classList.remove('active');
            }
        });
    }

    // --- Choices.js ---
    if (document.getElementById('spoken_languages')) {
        new Choices('#spoken_languages', { removeItemButton: true, placeholder: true });
    }

    // --- AOS Animation ---
    if (typeof AOS !== 'undefined') {
        AOS.init({ once: true, duration: 800, offset: 50 });
    }
});

// ==========================================
// 1. DASHBOARD LOGIC (Map + Charts)
// ==========================================

let barChartInstance = null, pieChartInstance = null, lineChartInstance = null;
let mapInstance = null; // Store map instance globally to prevent re-initialization issues

function initializeDashboard() {
    if (typeof Chart === 'undefined') return;
    
    // Initial Load
    fetchDashboardData();

    // Setup Filter Button
    const applyBtn = document.getElementById('apply-filters');
    if (applyBtn) {
        applyBtn.addEventListener('click', function() {
            const params = new URLSearchParams({
                'start_date': document.getElementById('date-start').value,
                'end_date': document.getElementById('date-end').value,
                // Note: api.py expects start_date/end_date, not date-start
            });
            fetchDashboardData(params.toString());
        });
    }
}

function fetchDashboardData(queryString = '') {
    const url = queryString ? `/dashboard-data?${queryString}` : '/dashboard-data';
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            // Render Charts
            if (data.bar_chart) renderBarChart(data.bar_chart);
            if (data.pie_chart) renderPieChart(data.pie_chart);
            if (data.line_chart) renderLineChart(data.line_chart);
            
            // Render Map (Only if map data exists and container is present)
            if (data.map_data && document.getElementById('nigeriaMap')) {
                initLeafletMap(data.map_data);
            }
        })
        .catch(err => console.error("Dashboard Load Error:", err));
}

// --- Chart Rendering Functions ---
function renderBarChart(data) {
    const ctx = document.getElementById('agentCallsChart').getContext('2d');
    if (barChartInstance) barChartInstance.destroy();
    barChartInstance = new Chart(ctx, { 
        type: 'bar', 
        data: { labels: data.labels, datasets: [{ label: 'Appointments', data: data.data, backgroundColor: '#2E7D32' }] },
        options: { responsive: true, maintainAspectRatio: false }
    });
}
function renderPieChart(data) {
    const ctx = document.getElementById('outcomesPieChart').getContext('2d');
    if (pieChartInstance) pieChartInstance.destroy();
    pieChartInstance = new Chart(ctx, { 
        type: 'doughnut', 
        data: { labels: data.labels, datasets: [{ data: data.data, backgroundColor: ['#2E7D32', '#FFC107', '#E53935', '#43A047', '#1E88E5'] }] },
        options: { responsive: true, maintainAspectRatio: false }
    });
}
function renderLineChart(data) {
    const ctx = document.getElementById('callVolumeLineChart').getContext('2d');
    if (lineChartInstance) lineChartInstance.destroy();
    lineChartInstance = new Chart(ctx, { 
        type: 'line', 
        data: { labels: data.labels, datasets: [{ label: 'Volume', data: data.data, borderColor: '#2E7D32', tension: 0.3, fill: false }] },
        options: { responsive: true, maintainAspectRatio: false }
    });
}

// --- Map Rendering Function (Moved from HTML) ---
function initLeafletMap(mapData) {
    // If map is already initialized, just clear layers (or remove it to rebuild)
    if (mapInstance) {
        mapInstance.remove();
    }

    // Initialize Map
    mapInstance = L.map('nigeriaMap').setView([9.0820, 8.6753], 6); 

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(mapInstance);

    // Hardcoded State Coordinates (Nigeria)
    const statesData = {
        "Abia": [5.4527, 7.5248], "Adamawa": [9.3265, 12.3984], "Akwa Ibom": [5.0515, 7.8467],
        "Anambra": [6.2209, 6.9370], "Bauchi": [10.7761, 9.9440], "Bayelsa": [4.7719, 6.0699],
        "Benue": [7.3369, 8.7404], "Borno": [11.8846, 13.1520], "Cross River": [5.8702, 8.5988],
        "Delta": [5.8904, 5.6806], "Ebonyi": [6.2649, 8.0137], "Edo": [6.5244, 5.8987],
        "Ekiti": [7.6674, 5.3783], "Enugu": [6.5364, 7.4356], "FCT": [9.0765, 7.3986],
        "Gombe": [10.2897, 11.1712], "Imo": [5.5720, 7.0588], "Jigawa": [12.2280, 9.5616],
        "Kaduna": [10.3764, 7.7093], "Kano": [11.7471, 8.5247], "Katsina": [12.9616, 7.6223],
        "Kebbi": [11.4942, 4.2336], "Kogi": [7.7337, 6.6906], "Kwara": [8.9669, 4.3874],
        "Lagos": [6.5244, 3.3792], "Nasarawa": [8.5475, 8.3520], "Niger": [9.9309, 5.6806],
        "Ogun": [7.1604, 3.3500], "Ondo": [7.2508, 5.1931], "Osun": [7.5629, 4.5200],
        "Oyo": [8.1574, 3.6147], "Plateau": [9.2182, 9.5179], "Rivers": [4.8156, 7.0498],
        "Sokoto": [13.0533, 5.2300], "Taraba": [7.9994, 10.5643], "Yobe": [12.0000, 11.5000],
        "Zamfara": [12.1221, 6.2236]
    };

    for (const [state, coords] of Object.entries(statesData)) {
        let dbName = state;
        if (state === 'FCT') dbName = 'Federal Capital Territory';

        // Get count from API data
        let count = mapData[dbName] || mapData[state] || 0;

        if (count > 0) {
            const numberIcon = L.divIcon({
                className: 'custom-number-icon',
                html: `<div class="map-digit-icon">${count}</div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            });

            L.marker(coords, { icon: numberIcon })
             .bindPopup(`<b>${state} State</b><br>Patients: ${count}`)
             .addTo(mapInstance);
        }
    }
}

// ==========================================
// 2. OTHER HELPER FUNCTIONS
// ==========================================

function initializePublicKpis() {
    try {
        const ids = ['kpi-patients-registered', 'kpi-appointments-confirmed', 'kpi-states-covered'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el && typeof CountUp !== 'undefined') {
                const count = parseInt(el.textContent.replace(/,/g, ''), 10) || 0;
                const anim = new CountUp(id, count);
                if (!anim.error) anim.start();
            }
        });
    } catch (e) { console.warn("KPI Animation failed:", e); }
}

function setupChatbot() {
    const chatWindow = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    let chatHistory = []; 

    function addMessage(sender, message, source = null) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender + '-message');
        const textElement = document.createElement('p');
        textElement.innerHTML = message.replace(/\n/g, '<br>');
        messageElement.appendChild(textElement);
        if (source) {
            const sourceElement = document.createElement('small');
            sourceElement.classList.add('source-citation');
            sourceElement.textContent = `Source: ${source}`;
            messageElement.appendChild(sourceElement);
        }
        chatWindow.appendChild(messageElement);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        chatHistory.push({ role: sender, content: message });
    }

    async function sendMessage() {
        const message = userInput.value.trim();
        if (message === '') return;
        addMessage('user', message);
        userInput.value = '';
        
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message bot-message';
        loadingDiv.innerHTML = '<em>Typing...</em>';
        chatWindow.appendChild(loadingDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        
        try {
            const response = await fetch('/chatbot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, history: chatHistory })
            });
            const data = await response.json();
            chatWindow.removeChild(loadingDiv);
            addMessage('bot', data.response, data.source);
        } catch (error) {
            chatWindow.removeChild(loadingDiv);
            addMessage('bot', 'Network error. Please try again.');
        }
    }
    if(sendButton) {
        sendButton.addEventListener('click', sendMessage);
        userInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); sendMessage(); } });
    }
}

function setupVolunteerQueueModal() {
    const modal = document.getElementById('notesModal');
    if (!modal) return;
    const closeBtn = modal.querySelector('.close-btn');
    window.openModal = function(caseId) { 
        const form = document.getElementById('completeCaseForm'); 
        form.action = `/complete-case/${caseId}`; 
        modal.style.display = 'block'; 
    }
    if(closeBtn) closeBtn.onclick = function() { modal.style.display = 'none'; };
    window.onclick = function(event) { if (event.target == modal) modal.style.display = 'none'; };
}

function setupLocationDropdowns() {
    const stateDropdown = document.getElementById('state');
    const lgaDropdown = document.getElementById('lga');
    if (!stateDropdown || !lgaDropdown) return;
    
    stateDropdown.addEventListener('change', function() {
        const stateId = this.value;
        lgaDropdown.innerHTML = '<option value="">Loading...</option>';
        if (!stateId) { lgaDropdown.innerHTML = '<option value="">-- Select a State First --</option>'; return; }
        
        fetch(`/api/lgas/${stateId}`)
            .then(response => response.json())
            .then(data => {
                lgaDropdown.innerHTML = '<option value="">-- Select an LGA --</option>';
                data.forEach(lga => { 
                    const option = document.createElement('option'); 
                    option.value = lga.id; option.textContent = lga.name; lgaDropdown.appendChild(option); 
                });
            })
            .catch(() => lgaDropdown.innerHTML = '<option value="">Error loading LGAs</option>');
    });
}

function setupSupaUserLocationFilter() {
    const stateFilter = document.getElementById('state-filter');
    const lgaFilter = document.getElementById('lga-filter');
    if (!stateFilter) return; // lga-filter might not exist in dashboard, that's fine

    stateFilter.addEventListener('change', async function() {
        const stateId = this.value;
        if(lgaFilter) lgaFilter.innerHTML = '<option value="all">All LGAs</option>';
        if (stateId && stateId !== 'all' && lgaFilter) {
            try {
                const response = await fetch(`/api/lgas/${stateId}`);
                const lgas = await response.json();
                lgas.forEach(lga => {
                    const option = document.createElement('option');
                    option.value = lga.id; option.textContent = lga.name; lgaFilter.appendChild(option);
                });
            } catch (e) { console.error("Filter Error", e); }
        }
    });
}