const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8001/api/v1").replace(/\/$/, "");

export async function fetchIncidents() {
  const response = await fetch(`${API_BASE}/incidents`);
  if (!response.ok) {
    throw new Error("Failed to load incidents");
  }
  return response.json();
}

export async function fetchContacts() {
  const response = await fetch(`${API_BASE}/contacts`);
  if (!response.ok) {
    throw new Error("Failed to load contacts");
  }
  return response.json();
}

export async function fetchCameraSources() {
  const response = await fetch(`${API_BASE}/camera-sources`);
  if (!response.ok) {
    throw new Error("Failed to load camera sources");
  }
  return response.json();
}

export async function createContact(payload) {
  const response = await fetch(`${API_BASE}/contacts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to create contact");
  }
  return response.json();
}

export async function deleteContact(contactId) {
  const response = await fetch(`${API_BASE}/contacts/${contactId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    let message = "Failed to delete admin contact";
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      }
    } catch {
      // Keep generic message.
    }
    throw new Error(message);
  }
  return response.json();
}

export async function analyzeIncident(formData) {
  const response = await fetch(`${API_BASE}/incidents/analyze`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    let message = "Failed to analyze incident";
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      }
    } catch {
      // Keep the generic message when the response body is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

export async function deleteIncident(incidentId) {
  const response = await fetch(`${API_BASE}/incidents/${incidentId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    let message = "Failed to delete incident";
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      }
    } catch {
      // Keep generic message.
    }
    throw new Error(message);
  }
  return response.json();
}
