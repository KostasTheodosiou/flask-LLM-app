let isGenerating = false;
let metricsVisible = true;
let metricsInterval;

function showStatus(message, isError = false) {
  const status = document.getElementById("status");
  status.textContent = message;
  status.className = "status show" + (isError ? " error" : "");
  setTimeout(() => {
    status.className = "status";
  }, 3000);
}

function addMessage(content, isUser = false) {
  const chatContainer = document.getElementById("chatContainer");
  const messageDiv = document.createElement("div");
  messageDiv.className = `message ${isUser ? "user-message" : "assistant-message"
    }`;
  messageDiv.textContent = content;
  chatContainer.appendChild(messageDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function showTypingIndicator() {
  const chatContainer = document.getElementById("chatContainer");
  const typingDiv = document.createElement("div");
  typingDiv.className = "typing-indicator show";
  typingDiv.id = "typingIndicator";
  typingDiv.innerHTML =
    '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  chatContainer.appendChild(typingDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function hideTypingIndicator() {
  const typingIndicator = document.getElementById("typingIndicator");
  if (typingIndicator) {
    typingIndicator.remove();
  }
}

function toggleMetrics() {
  const content = document.getElementById("metricsContent");
  const toggle = document.getElementById("metricsToggle");

  metricsVisible = !metricsVisible;

  if (metricsVisible) {
    content.classList.remove("metrics-hidden");
    toggle.textContent = "Hide Metrics";
  } else {
    content.classList.add("metrics-hidden");
    toggle.textContent = "Show Metrics";
  }
}

function formatValue(value, type) {
  if (value === null || value === undefined) return "--";

  switch (type) {
    case 'time':
      return `${value}s`;
    case 'tokens':
      return `${value.toFixed(1)} t/s`;
    case 'percentage':
      return `${(value * 100).toFixed(1)}%`;
    case 'memory':
      return `${(value / 1024 / 1024).toFixed(1)} MB`;
    case 'boolean':
      return value ? "Loaded" : "Not Loaded";
    default:
      return value.toString();
  }
}

function updateMetrics() {
  fetch("/metrics")
    .then(response => response.json())
    .then(data => {
      const statusIndicator = document.getElementById("metricsStatus");
      statusIndicator.className = "status-indicator online";
      if (data.aggregate) {
        // Update aggregate metrics
        document.getElementById("avgTimeToFirstToken").textContent =
          formatValue(data.aggregate.avg_time_to_first_token, 'time');
        document.getElementById("avgTokensPerSecond").textContent =
          formatValue(data.aggregate.avg_tokens_per_second, 'tokens');

        // const errorRate = document.getElementById("errorRate");
        // errorRate.textContent = formatValue(data.aggregate.error_rate, 'percentage');
        // errorRate.className = "metric-value " + (data.aggregate.error_rate > 0.1 ? "error" : "good");

        document.getElementById("totalRequests").textContent =
          formatValue(data.aggregate.total_requests);
      }

      // if (data.system) {
      //   // Update system information
      //   document.getElementById("memoryUsage").textContent = 
      //     formatValue(data.system.memory_usage, 'memory');
      //   document.getElementById("gpuUsage").textContent = 
      //     data.system.gpu_usage || "--";
      //   document.getElementById("totalErrors").textContent = 
      //     formatValue(data.system.errors);
      //   document.getElementById("recentRequests").textContent = 
      //     formatValue(data.recent_requests_count);
      // }

      // Update last updated time
      document.getElementById("lastUpdated").textContent =
        "Last updated: " + new Date().toLocaleTimeString();
    })
    .catch(error => {
      console.error("Error fetching metrics:", error);
      const statusIndicator = document.getElementById("metricsStatus");
      statusIndicator.className = "status-indicator offline";
    });
}

async function sendMessage() {
  const promptInput = document.getElementById("promptInput");
  const sendBtn = document.getElementById("sendBtn");
  const maxTokens = document.getElementById("maxTokens").value;
  const temperature = document.getElementById("temperature").value;

  const prompt = promptInput.value.trim();
  if (!prompt) return;

  if (isGenerating) {
    showStatus("Please wait for the current response to complete", true);
    return;
  }

  // Add user message
  addMessage(prompt, true);
  promptInput.value = "";

  // Show loading state
  isGenerating = true;
  sendBtn.disabled = true;
  sendBtn.textContent = "Generating...";
  showTypingIndicator();

  try {
    console.log("Sending request to server with prompt:", prompt);
    const response = await fetch("/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt: prompt,
        max_tokens: parseInt(maxTokens),
        temperature: parseFloat(temperature),
      }),
    });

    hideTypingIndicator();

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let assistantResponse = "";

    // Create assistant message container
    const chatContainer = document.getElementById("chatContainer");
    const messageDiv = document.createElement("div");
    messageDiv.className = "message assistant-message";
    chatContainer.appendChild(messageDiv);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") {
            break;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) {
              assistantResponse += parsed.token;
              messageDiv.textContent = assistantResponse;
              chatContainer.scrollTop = chatContainer.scrollHeight;
            }
          } catch (e) {
            // Ignore parsing errors for incomplete JSON
          }
        }
      }
    }
    setTimeout(updateMetrics, 500);
  } catch (error) {
    hideTypingIndicator();
    console.error("Error:", error);
    addMessage(
      "Sorry, there was an error processing your request. Please try again.",
      false
    );
    showStatus("Error: " + error.message, true);
  } finally {
    isGenerating = false;
    sendBtn.disabled = false;
    sendBtn.textContent = "Send";
  }
}

// Allow Enter to send message (Shift+Enter for new line)
document
  .getElementById("promptInput")
  .addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

// Auto-resize textarea
document
  .getElementById("promptInput")
  .addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 120) + "px";
  });

// Initialize
document.addEventListener("DOMContentLoaded", function () {
  showStatus("Model loading... Please wait before sending messages.");

  // Check if model is ready
  fetch("/health")
    .then((response) => response.json())
    .then((data) => {
      if (data.status === "ready") {
        showStatus("Model ready! You can start chatting.");
      } else {
        showStatus("Model is still loading... Please wait.");
      }
    })
    .catch((error) => {
      showStatus("Error checking model status", true);
    });

  updateMetrics();
});

// Add these functions to your existing script.js

let currentModelId = null;
let isModelSwitching = false;

// Load available models on page load
async function loadAvailableModels() {
  try {
    const response = await fetch('/models/available');
    const data = await response.json();

    const select = document.getElementById('modelSelect');
    select.innerHTML = '';

    data.models.forEach(model => {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = model.display_name;
      if (model.id === data.current_model) {
        option.selected = true;
        currentModelId = model.id;
      }
      select.appendChild(option);
    });

    updateModelStatus();
  } catch (error) {
    console.error('Failed to load models:', error);
    document.getElementById('modelSelect').innerHTML = '<option>Error loading models</option>';
  }
}

// Switch to selected model
async function switchModel() {
  const select = document.getElementById('modelSelect');
  const newModelId = select.value;

  if (newModelId === currentModelId || isModelSwitching) {
    return;
  }

  if (!confirm(`Switch to ${select.options[select.selectedIndex].text}? This will reload the model.`)) {
    select.value = currentModelId;
    return;
  }

  isModelSwitching = true;
  const statusEl = document.getElementById('modelLoadStatus');
  statusEl.textContent = '🔄 Switching...';
  statusEl.className = 'model-status switching';

  // Disable send button
  document.getElementById('sendBtn').disabled = true;

  try {
    const response = await fetch('/models/switch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ model_id: newModelId })
    });

    const data = await response.json();

    if (response.ok) {
      // Poll for model load completion
      pollModelStatus(newModelId);
    } else {
      throw new Error(data.error || 'Failed to switch model');
    }
  } catch (error) {
    console.error('Model switch failed:', error);
    statusEl.textContent = '❌ Switch failed';
    statusEl.className = 'model-status error';
    select.value = currentModelId;
    isModelSwitching = false;
    document.getElementById('sendBtn').disabled = false;
  }
}

// Poll model status until loaded
async function pollModelStatus(targetModelId) {
  const statusEl = document.getElementById('modelLoadStatus');

  const checkStatus = async () => {
    try {
      const response = await fetch('/models/current');
      const data = await response.json();

      if (data.loading_error) {
        statusEl.textContent = '❌ Load failed';
        statusEl.className = 'model-status error';
        isModelSwitching = false;
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('modelSelect').value = currentModelId;
        return;
      }

      if (data.loaded && data.model_id === targetModelId) {
        currentModelId = targetModelId;
        statusEl.textContent = '✓ Ready';
        statusEl.className = 'model-status ready';
        isModelSwitching = false;
        document.getElementById('sendBtn').disabled = false;

        // Add system message to chat
        const chatContainer = document.getElementById('chatContainer');
        const systemMsg = document.createElement('div');
        systemMsg.className = 'message system-message';
        systemMsg.textContent = `Switched to ${data.display_name}`;
        chatContainer.appendChild(systemMsg);
        chatContainer.scrollTop = chatContainer.scrollHeight;
      } else {
        // Still loading, check again
        setTimeout(checkStatus, 500);
      }
    } catch (error) {
      console.error('Status check failed:', error);
      setTimeout(checkStatus, 1000);
    }
  };

  checkStatus();
}

// Update model status indicator
async function updateModelStatus() {
  try {
    const response = await fetch('/models/current');
    const data = await response.json();

    const statusEl = document.getElementById('modelLoadStatus');

    if (data.loading_error) {
      statusEl.textContent = '❌ Error';
      statusEl.className = 'model-status error';
    } else if (data.loaded) {
      statusEl.textContent = '✓ Ready';
      statusEl.className = 'model-status ready';
      currentModelId = data.model_id;
    } else {
      statusEl.textContent = `⏳ ${data.loading_progress}%`;
      statusEl.className = 'model-status loading';
      setTimeout(updateModelStatus, 1000);
    }
  } catch (error) {
    console.error('Failed to check model status:', error);
  }
}

// Modify the existing sendMessage function to check if model is switching
const originalSendMessage = sendMessage;
sendMessage = function () {
  if (isModelSwitching) {
    alert('Please wait for the model to finish loading');
    return;
  }
  originalSendMessage();
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
  loadAvailableModels();

  // Check model status periodically
  setInterval(updateModelStatus, 20000);
});

async function loadNodeName() {
  try {
    const response = await fetch('/node-info');
    const data = await response.json();
    document.getElementById('nodeNameDisplay').textContent = data.node_name;
  } catch (error) {
    console.error('Failed to load node name:', error);
    document.getElementById('nodeNameDisplay').textContent = 'Error loading';
  }
}

// Call this when the page loads
document.addEventListener('DOMContentLoaded', loadNodeName);