import axios from "axios";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

export function login(email, password) {
  return axios.post(`${BACKEND}/login`, { email, password });
}

export function uploadFile(file, token) {
  const fd = new FormData();
  fd.append("file", file);
  return axios.post(`${BACKEND}/upload`, fd, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "multipart/form-data",
    },
  });
}

export function analyzeText(text, token) {
  return axios.post(`${BACKEND}/analyze`, { text }, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function analyzeStored(stored_filename, token) {
  return axios.post(`${BACKEND}/analyze`, { stored_filename }, {
    headers: { Authorization: `Bearer ${token}` },
  });
}
