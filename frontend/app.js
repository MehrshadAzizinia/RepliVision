// Configuration
const API_BASE_URL = 'http://localhost:5000/api';

// Global state
let models = [];
let selectedModel = null;
let plyData = null;
let rotation = { x: 0.3, y: 0.3 };
let isDragging = false;
let lastPos = { x: 0, y: 0 };
let autoRotate = true;
let animationId = null;

// DOM Elements
const loadingEl = document.getElementById('loading');
const errorEl = document.getElementById('error');
const errorTextEl = document.getElementById('error-text');
const modelGridEl = document.getElementById('model-grid');
const emptyStateEl = document.getElementById('empty-state');
const viewerModal = document.getElementById('viewer-modal');
const modalTitle = document.getElementById('modal-title');
const modalDescription = document.getElementById('modal-description');
const closeModalBtn = document.getElementById('close-modal');
const viewerCanvas = document.getElementById('viewer-canvas');
const viewerLoading = document.getElementById('viewer-loading');
const controlText = document.getElementById('control-text');
const resetButton = document.getElementById('reset-button');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    closeModalBtn.addEventListener('click', closeModal);
    resetButton.addEventListener('click', resetRotation);
    
    viewerCanvas.addEventListener('mousedown', handleMouseDown);
    viewerCanvas.addEventListener('mousemove', handleMouseMove);
    viewerCanvas.addEventListener('mouseup', handleMouseUp);
    viewerCanvas.addEventListener('mouseleave', handleMouseUp);
    
    // Close modal on background click
    viewerModal.addEventListener('click', (e) => {
        if (e.target === viewerModal) {
            closeModal();
        }
    });
}

// API Functions
async function loadModels() {
    try {
        showLoading();
        hideError();
        
        const response = await fetch(`${API_BASE_URL}/list-models`);
        
        if (!response.ok) {
            throw new Error('Failed to load models');
        }
        
        const data = await response.json();
        
        if (data.success) {
            models = data.models;
            renderModels();
        } else {
            throw new Error(data.error || 'Unknown error');
        }
        
    } catch (error) {
        showError('Error loading models: ' + error.message);
        showEmptyState();
    } finally {
        hideLoading();
    }
}

async function loadModelData(model) {
    try {
        const response = await fetch(
            `${API_BASE_URL}/get-model?fileId=${model.fileId}&name=${model.id}`
        );
        
        if (!response.ok) {
            throw new Error('Failed to load model data');
        }
        
        const text = await response.text();
        return parsePLY(text);
        
    } catch (error) {
        console.error('Error loading model data:', error);
        // Return demo data on error
        return generateDemoData(model.vertices);
    }
}

// PLY Parser
function parsePLY(text) {
    const lines = text.split('\n');
    let vertexCount = 0;
    let properties = [];
    const vertices = [];
    
    // Parse header
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        
        if (line.startsWith('element vertex')) {
            vertexCount = parseInt(line.split(' ')[2]);
        } else if (line.startsWith('property')) {
            properties.push(line.split(' ')[2]);
        } else if (line === 'end_header') {
            // Parse vertex data
            for (let j = i + 1; j < i + 1 + vertexCount && j < lines.length; j++) {
                const values = lines[j].trim().split(/\s+/).map(v => parseFloat(v));
                if (values.length >= 3) {
                    const vertex = {
                        x: values[0],
                        y: values[1],
                        z: values[2]
                    };
                    
                    if (values.length >= 6) {
                        vertex.r = values[3];
                        vertex.g = values[4];
                        vertex.b = values[5];
                    }
                    
                    vertices.push(vertex);
                }
            }
            break;
        }
    }
    
    return { vertices, properties, vertexCount };
}

// Generate demo data for fallback
function generateDemoData(vertexCount) {
    const count = Math.min(vertexCount, 10000);
    const vertices = [];
    
    for (let i = 0; i < count; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.random() * Math.PI;
        const r = Math.random() * 50 + 30;
        
        vertices.push({
            x: r * Math.sin(phi) * Math.cos(theta),
            y: r * Math.sin(phi) * Math.sin(theta),
            z: r * Math.cos(phi),
            r: Math.floor(Math.random() * 100 + 155),
            g: Math.floor(Math.random() * 100 + 100),
            b: Math.floor(Math.random() * 100 + 200)
        });
    }
    
    return { vertices, vertexCount: count };
}

// Rendering Functions
function renderModels() {
    modelGridEl.innerHTML = '';
    
    if (models.length === 0) {
        showEmptyState();
        return;
    }
    
    hideEmptyState();
    
    models.forEach(model => {
        const card = createModelCard(model);
        modelGridEl.appendChild(card);
    });
}

function createModelCard(model) {
    const card = document.createElement('div');
    card.className = 'model-card';
    
    card.innerHTML = `
        <div class="model-thumbnail">
            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                <line x1="12" y1="22.08" x2="12" y2="12"></line>
            </svg>
        </div>
        <div class="model-info">
            <h3 class="model-name">${model.name}</h3>
            <p class="model-description">${model.description}</p>
            
            <div class="model-stats">
                <div class="stat-box">
                    <div class="stat-header cyan">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                        </svg>
                        <span class="stat-label">Vertices</span>
                    </div>
                    <p class="stat-value">${model.vertices.toLocaleString()}</p>
                </div>
                <div class="stat-box">
                    <div class="stat-header emerald">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
                        </svg>
                        <span class="stat-label">Size</span>
                    </div>
                    <p class="stat-value">${model.fileSize}</p>
                </div>
            </div>
            
            <div class="model-date">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                    <line x1="16" y1="2" x2="16" y2="6"></line>
                    <line x1="8" y1="2" x2="8" y2="6"></line>
                    <line x1="3" y1="10" x2="21" y2="10"></line>
                </svg>
                <span>${model.createdAt}</span>
            </div>
            
            <button class="preview-button">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                </svg>
                <span>Preview 3D Model</span>
            </button>
        </div>
    `;
    
    card.querySelector('.preview-button').addEventListener('click', () => {
        openViewer(model);
    });
    
    return card;
}

// Viewer Functions
async function openViewer(model) {
    selectedModel = model;
    modalTitle.textContent = model.name;
    modalDescription.textContent = model.description;
    
    viewerModal.style.display = 'flex';
    viewerLoading.style.display = 'flex';
    viewerCanvas.classList.remove('active');
    
    autoRotate = true;
    rotation = { x: 0.3, y: 0.3 };
    
    // Load model data
    plyData = await loadModelData(model);
    
    // Show canvas and hide loading
    viewerLoading.style.display = 'none';
    viewerCanvas.classList.add('active');
    
    // Start rendering
    renderPointCloud();
    startAnimation();
}

function closeModal() {
    viewerModal.style.display = 'none';
    stopAnimation();
    selectedModel = null;
    plyData = null;
}

function resetRotation() {
    rotation = { x: 0.3, y: 0.3 };
    autoRotate = true;
    updateControlText();
}

// Point Cloud Rendering
function renderPointCloud() {
    if (!plyData || !plyData.vertices || plyData.vertices.length === 0) return;
    
    const canvas = viewerCanvas;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    // Clear canvas
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, width, height);
    
    const vertices = plyData.vertices;
    
    // Calculate bounds
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    
    vertices.forEach(v => {
        minX = Math.min(minX, v.x);
        maxX = Math.max(maxX, v.x);
        minY = Math.min(minY, v.y);
        maxY = Math.max(maxY, v.y);
        minZ = Math.min(minZ, v.z);
        maxZ = Math.max(maxZ, v.z);
    });
    
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const centerZ = (minZ + maxZ) / 2;
    const scale = Math.min(width, height) / (Math.max(maxX - minX, maxY - minY, maxZ - minZ) * 1.5);
    
    // Rotation matrices
    const cosX = Math.cos(rotation.x);
    const sinX = Math.sin(rotation.x);
    const cosY = Math.cos(rotation.y);
    const sinY = Math.sin(rotation.y);
    
    // Project and sort vertices
    const projected = vertices.map(v => {
        // Center
        let x = v.x - centerX;
        let y = v.y - centerY;
        let z = v.z - centerZ;
        
        // Rotate around Y axis
        let x1 = x * cosY - z * sinY;
        let z1 = x * sinY + z * cosY;
        
        // Rotate around X axis
        let y2 = y * cosX - z1 * sinX;
        let z2 = y * sinX + z1 * cosX;
        
        return {
            x: x1 * scale + width / 2,
            y: y2 * scale + height / 2,
            z: z2,
            color: v.r !== undefined ? `rgb(${v.r}, ${v.g}, ${v.b})` : null
        };
    });
    
    // Sort by depth for proper rendering
    projected.sort((a, b) => a.z - b.z);
    
    // Draw points
    projected.forEach(p => {
        const size = Math.max(1, 2.5 - p.z / 100);
        ctx.fillStyle = p.color || '#06b6d4';
        ctx.beginPath();
        ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
        ctx.fill();
    });
}

// Animation
function startAnimation() {
    stopAnimation();
    
    function animate() {
        if (autoRotate) {
            rotation.y += 0.008;
            renderPointCloud();
        }
        animationId = requestAnimationFrame(animate);
    }
    
    animate();
}

function stopAnimation() {
    if (animationId) {
        cancelAnimationFrame(animationId);
        animationId = null;
    }
}

// Mouse Handlers
function handleMouseDown(e) {
    isDragging = true;
    autoRotate = false;
    lastPos = { x: e.clientX, y: e.clientY };
    updateControlText();
}

function handleMouseMove(e) {
    if (!isDragging) return;
    
    const dx = e.clientX - lastPos.x;
    const dy = e.clientY - lastPos.y;
    
    rotation.y += dx * 0.01;
    rotation.x += dy * 0.01;
    
    lastPos = { x: e.clientX, y: e.clientY };
    renderPointCloud();
}

function handleMouseUp() {
    isDragging = false;
}

function updateControlText() {
    controlText.textContent = `Drag to rotate • ${autoRotate ? 'Auto-rotating' : 'Manual control'}`;
}

// UI Helper Functions
function showLoading() {
    loadingEl.style.display = 'block';
}

function hideLoading() {
    loadingEl.style.display = 'none';
}

function showError(message) {
    errorTextEl.textContent = message;
    errorEl.style.display = 'block';
}

function hideError() {
    errorEl.style.display = 'none';
}

function showEmptyState() {
    emptyStateEl.style.display = 'block';
    modelGridEl.style.display = 'none';
}

function hideEmptyState() {
    emptyStateEl.style.display = 'none';
    modelGridEl.style.display = 'grid';
}