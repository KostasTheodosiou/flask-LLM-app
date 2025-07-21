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
  messageDiv.className = `message ${
    isUser ? "user-message" : "assistant-message"
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
