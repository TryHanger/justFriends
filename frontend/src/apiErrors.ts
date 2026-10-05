function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!isRecord(error) || !isRecord(error.response) || !isRecord(error.response.data)) {
    return fallback;
  }

  const detail = error.response.data.detail;
  if (typeof detail === 'string') return detail.trim() || fallback;

  if (Array.isArray(detail)) {
    const messages = detail.flatMap(issue => {
      if (!isRecord(issue) || typeof issue.msg !== 'string') return [];
      const message = issue.msg.trim();
      return message ? [message] : [];
    });
    return messages.join('; ') || fallback;
  }

  return fallback;
}
