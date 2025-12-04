document.addEventListener('DOMContentLoaded', function() {
    // --- Safe Initialization ---
    // Only run logic if elements exist to prevent console errors
    
    if (document.getElementById('agentCallsChart')) initializeDashboard();
    if (document.getElementById('send-button')) setupChatbot();
    if (document.getElementById('kpi-patients-registered')) initializePublicKpis();
    if (document.getElementById('notesModal')) setupVolunteerQueueModal();
    if (document.getElementById('state')) setupLocationDropdowns();
    if (document.getElementById('state-filter')) setupSupaUserLocationFilter();

    // --- SIDEBAR TOGGLE LOGIC ---
    if (document.getElementById('menu-toggle')) {
        const menuToggle = document.getElementById('menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        const navLinks = document.querySelectorAll('.nav-links a');

        // Toggle Open/Close
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent bubbling
            sidebar.classList.toggle('active');
            if (overlay) overlay.classList.toggle('active');
        });

        // Close when clicking overlay
        if (overlay) {
            overlay.addEventListener('click', () => {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            });
        }

        // Auto-close when clicking a link on mobile
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth <= 992) {
                    sidebar.classList.remove('active');
                    if (overlay) overlay.classList.remove('active');
                }
            });
        });

        // Reset on Resize (e.g. rotating tablet)
        window.addEventListener('resize', () => {
            if (window.innerWidth > 992) {
                sidebar.classList.remove('active');
                if (overlay) overlay.classList.remove('active');
            }
        });
    }

    // --- Choices.js for Nice Dropdowns ---
    if (document.getElementById('spoken_languages')) {
        new Choices('#spoken_languages', {
            removeItemButton: true,
            placeholder: true,
            placeholderValue: 'Select languages...'
        });
    }

    // --- AOS Animation ---
    if (typeof AOS !== 'undefined') {
        AOS.init({
            once: true,
            duration: 800,
            offset: 50,
            disable: window.innerWidth < 400 
        });
    }
});

// --- HELPER FUNCTIONS ---

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
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); sendMessage(); } });
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
    if (!stateFilter || !lgaFilter) return;

    stateFilter.addEventListener('change', async function() {
        const stateId = this.value;
        lgaFilter.innerHTML = '<option value="all">All LGAs</option>';
        if (stateId && stateId !== 'all') {
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

function initializeDashboard() {
    if (typeof Chart === 'undefined') return;
    fetchDashboardData();
    const applyBtn = document.getElementById('apply-filters');
    if (applyBtn) {
        applyBtn.addEventListener('click', function() {
            const params = new URLSearchParams({
                'date-start': document.getElementById('date-start').value,
                'date-end': document.getElementById('date-end').value,
                'service-type-filter': document.getElementById('service-type-filter').value,
                'state-filter': document.getElementById('state-filter')?.value || 'all',
                'lga-filter': document.getElementById('lga-filter')?.value || 'all'
            });
            fetchDashboardData(params.toString());
        });
    }
}

let barChartInstance = null, pieChartInstance = null, lineChartInstance = null;

function fetchDashboardData(queryString = '') {
    fetch(queryString ? `/dashboard-data?${queryString}` : '/dashboard-data')
        .then(response => response.json())
        .then(data => {
            if (data.bar_chart) renderBarChart(data.bar_chart);
            if (data.pie_chart) renderPieChart(data.pie_chart);
            if (data.line_chart) renderLineChart(data.line_chart);
        });
}

function renderBarChart(data) {
    const ctx = document.getElementById('agentCallsChart').getContext('2d');
    if (barChartInstance) barChartInstance.destroy();
    barChartInstance = new Chart(ctx, { type: 'bar', data: { labels: data.labels, datasets: [{ label: 'Appointments', data: data.data, backgroundColor: '#2E7D32' }] } });
}
function renderPieChart(data) {
    const ctx = document.getElementById('outcomesPieChart').getContext('2d');
    if (pieChartInstance) pieChartInstance.destroy();
    pieChartInstance = new Chart(ctx, { type: 'pie', data: { labels: data.labels, datasets: [{ data: data.data, backgroundColor: ['#2E7D32', '#FFC107', '#E53935', '#43A047'] }] } });
}
function renderLineChart(data) {
    const ctx = document.getElementById('callVolumeLineChart').getContext('2d');
    if (lineChartInstance) lineChartInstance.destroy();
    lineChartInstance = new Chart(ctx, { type: 'line', data: { labels: data.labels, datasets: [{ label: 'Volume', data: data.data, borderColor: '#2E7D32', tension: 0.1 }] } });
}