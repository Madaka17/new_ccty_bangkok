// The subscriber line under "เครื่องนี้" on the alerts page. Zero or missing means nothing to say.
export function subscriberSentence(status) {
  const n = status?.subscribers;
  return n > 0 ? ` · มีคนเปิดรับแจ้งเตือน ${n} เครื่อง` : '';
}
