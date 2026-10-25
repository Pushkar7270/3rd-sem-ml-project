export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (response.status === 204) return null;
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    if (data?.detail) {
      if (Array.isArray(data.detail)) {
        message = data.detail
          .map((item) => `${(item.loc || []).slice(1).join(".") || "field"}: ${item.msg}`)
          .join("\n");
      } else {
        message = String(data.detail);
      }
    }
    throw new Error(message);
  }
  return data;
}
