// --- script.js (Complete file for copy-paste) ---

document.addEventListener('DOMContentLoaded', function() {
    // Initialize functions based on what's present on the current page
    if (document.getElementById('agentCallsChart')) initializeDashboard();
    if (document.getElementById('send-button')) setupChatbot();
    // KPI LOGIC: Initialized directly on the server-rendered content
    if (document.getElementById('kpi-patients-registered')) initializePublicKpis();
    if (document.getElementById('notesModal')) setupVolunteerQueueModal();
    if (document.getElementById('state')) setupLocationDropdowns();
    if (document.getElementById('state-filter')) setupSupaUserLocationFilter();
    if (document.getElementById('menu-toggle')) setupSidebarToggle();

    // Merged: Choices.js initializer for the language dropdown
    if (document.getElementById('spoken_languages')) {
        new Choices('#spoken_languages', {
            removeItemButton: true,
            placeholder: true,
            placeholderValue: 'Select languages...'
        });
    }

    // Initialize Animate on Scroll (AOS) Library
    if (typeof AOS !== 'undefined') {
        AOS.init({ once: true, duration: 800 });
    }
});

// --- 1. SIDEBAR TOGGLE ---
function setupSidebarToggle() {
    const menuToggle = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    
    menuToggle.addEventListener('click', () => {
        // Mobile behavior (below 992px): Toggle slide-out menu
        if (window.innerWidth <= 992) {
            sidebar.classList.toggle('active');
        } else {
            // Desktop behavior (above 992px): Toggle collapse/expand
            sidebar.classList.toggle('collapsed');
            mainContent.classList.toggle('sidebar-collapsed');
        }
    });

    // Handle initial load and resize events to prevent mixed states
    window.addEventListener('load', () => {
        if (window.innerWidth > 992) {
            // Default desktop state: expanded
            sidebar.classList.remove('active');
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('sidebar-collapsed');
        }
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth > 992) {
            // Ensure mobile-only class is off
            sidebar.classList.remove('active'); 
        } else {
            // Ensure desktop-only classes are off when on mobile
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('sidebar-collapsed');
        }
    });
}

// --- 2. DASHBOARD LOGIC ---
function initializeDashboard() {
    fetchDashboardData();
    updateHistogram();
}

function fetchDashboardData() {
    fetch('/dashboard-data') 
        .then(response => response.json())
        .then(data => {
            if (data.bar_chart) renderBarChart(data.bar_chart);
            if (data.pie_chart) renderPieChart(data.pie_chart);
            if (data.line_chart) renderLineChart(data.line_chart);
        })
        .catch(error => console.error('Error fetching dashboard data:', error));
}

Chart.defaults.color = '#212121';
Chart.defaults.borderColor = '#E0E0E0';

function renderBarChart(data) {
    const ctx = document.getElementById('agentCallsChart').getContext('2d');
    new Chart(ctx, { type: 'bar', data: { labels: data.labels, datasets: [{ label: 'Number of Calls', data: data.data, backgroundColor: ['#1DE9B6', '#A0D2EB'], borderWidth: 1, borderRadius: 5 }] } });
}

function renderPieChart(data) {
    const ctx = document.getElementById('outcomesPieChart').getContext('2d');
    new Chart(ctx, { type: 'pie', data: { labels: data.labels, datasets: [{ data: data.data, backgroundColor: ['#1DE9B6', '#4DD0E1', '#FFD54F', '#FF8A65', '#90A4AE', '#7986CB'] }] } });
}

function renderLineChart(data) {
    const ctx = document.getElementById('callVolumeLineChart').getContext('2d');
    new Chart(ctx, { type: 'line', data: { labels: data.labels, datasets: [{ label: 'Call Volume', data: data.data, fill: false, borderColor: '#1DE9B6', tension: 0.1 }] } });
}

let histogramChart;
function updateHistogram() {
    const params = new URLSearchParams();
    params.append('start_date', document.getElementById('date-start').value);
    params.append('end_date', document.getElementById('date-end').value);
    params.append('service_type', document.getElementById('service-type-filter').value);
    params.append('status', document.getElementById('status-filter').value);
    const lgaFilter = document.getElementById('lga-filter')?.value || document.getElementById('lga-filter-supa')?.value;
    const stateFilter = document.getElementById('state-filter')?.value;
    if (lgaFilter) params.append('lga_id', lgaFilter);
    if (stateFilter) params.append('state_id', stateFilter);
    fetch(`/histogram-data?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            if (histogramChart) histogramChart.destroy();
            const ctx = document.getElementById('serviceHistogramChart').getContext('2d');
            histogramChart = new Chart(ctx, { type: 'bar', data: { labels: data.labels, datasets: [{ label: 'Service Count', data: data.data, backgroundColor: '#4DD0E1', borderWidth: 1, borderRadius: 5 }] } });
        })
        .catch(error => console.error('Error fetching histogram data:', error));
}

function setupSupaUserLocationFilter() {
    const stateFilter = document.getElementById('state-filter');
    const lgaFilter = document.getElementById('lga-filter-supa');
    stateFilter.addEventListener('change', function() {
        const stateId = this.value;
        lgaFilter.innerHTML = '<option value="">Loading...</option>';
        lgaFilter.disabled = true;
        if (!stateId || stateId === 'all') {
            lgaFilter.innerHTML = '<option value="all">All LGAs</option>';
            lgaFilter.disabled = false; return;
        }
        fetch(`/api/lgas/${stateId}`)
            .then(response => response.json())
            .then(data => {
                lgaFilter.innerHTML = '<option value="all">All LGAs</option>';
                data.forEach(lga => { const option = document.createElement('option'); option.value = lga.id; option.textContent = lga.name; lgaFilter.appendChild(option); });
                lgaFilter.disabled = false;
            })
            .catch(error => console.error('Error fetching LGAs:', error));
    });
}

// --- 3. PUBLIC KPI LOGIC (SIMPLE DISPLAY) ---
function initializePublicKpis() {
    // Logic to animate the server-side rendered data.
    try {
        const patients_element = document.getElementById('kpi-patients-registered');
        const appointments_element = document.getElementById('kpi-appointments-confirmed');
        const states_element = document.getElementById('kpi-states-covered');

        // Read the target count directly from the server-rendered HTML content
        const patients_count = Number(patients_element.textContent) || 0;
        const appointments_count = Number(appointments_element.textContent) || 0;
        const states_count = Number(states_element.textContent) || 0;

        // Initialize CountUp to animate from 0 up to the number already rendered by Jinja
        const patients = new CountUp('kpi-patients-registered', patients_count, { startVal: 0 });
        const appointments = new CountUp('kpi-appointments-confirmed', appointments_count, { startVal: 0 });
        const states = new CountUp('kpi-states-covered', states_count, { startVal: 0 });
        
        // Start the animation
        if (!patients.error) patients.start();
        if (!appointments.error) appointments.start();
        if (!states.error) states.start();
    } catch(e) {
        console.error("Error running CountUp animation on server-side rendered data:", e);
    }
}

// --- 4. CHATBOT LOGIC ---
function setupChatbot() {
    const chatWindow = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    let chatHistory = []; 

    function addMessage(sender, message, source = null) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender + '-message');
        const textElement = document.createElement('p');
        textElement.textContent = message;
        messageElement.appendChild(textElement);
        if (source) {
            const sourceElement = document.createElement('small');
            sourceElement.classList.add('source-citation');
            sourceElement.textContent = `Source: ${source}`;
            messageElement.appendChild(sourceElement);
        }
        chatWindow.appendChild(messageElement);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        if (message !== 'Typing...') {
            chatHistory.push({ role: sender, content: message });
        }
    }

    async function sendMessage() {
        const message = userInput.value.trim();
        if (message === '') return;
        addMessage('user', message);
        userInput.value = '';
        addMessage('bot', 'Typing...');
        
        try {
            const response = await fetch('/chatbot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, history: chatHistory.slice(0, -1) })
            });
            const data = await response.json();
            chatWindow.removeChild(chatWindow.lastChild);
            addMessage('bot', data.response, data.source);
        } catch (error) {
            console.error('Error:', error);
            chatWindow.removeChild(chatWindow.lastChild);
            addMessage('bot', 'Sorry, I am having trouble connecting. Please try again later.');
        }
    }

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); sendMessage(); } });
}

// --- 5. VOLUNTEER QUEUE MODAL LOGIC ---
function setupVolunteerQueueModal() {
    const modal = document.getElementById('notesModal');
    if (!modal) return;
    const closeBtn = modal.querySelector('.close-btn');
    window.openModal = function(caseId) { const form = document.getElementById('completeCaseForm'); form.action = `/complete-case/${caseId}`; modal.style.display = 'block'; }
    if(closeBtn) { closeBtn.onclick = function() { modal.style.display = 'none'; } }
    window.onclick = function(event) { if (event.target == modal) { modal.style.display = 'none'; } }
}

// --- 6. DYNAMIC LOCATION DROPDOWNS ---
function setupLocationDropdowns() {
    const stateDropdown = document.getElementById('state');
    const lgaDropdown = document.getElementById('lga');
    if (!stateDropdown || !lgaDropdown) return;
    stateDropdown.addEventListener('change', function() {
        const stateId = this.value;
        lgaDropdown.innerHTML = '<option value="">Loading...</option>';
        if (!stateId) { lgaDropdown.innerHTML = '<option value="">-- Select a State First --</option>'; return; }
        fetch(`/api/lgas/${stateId}`).then(response => response.json()).then(data => {
            lgaDropdown.innerHTML = '<option value="">-- Select an LGA --</option>';
            data.forEach(lga => { const option = document.createElement('option'); option.value = lga.id; option.textContent = lga.name; lgaDropdown.appendChild(option); });
        }).catch(error => { console.error('Error fetching LGAs:', error); lgaDropdown.innerHTML = '<option value="">-- Error loading LGAs --</option>'; });
    });
}