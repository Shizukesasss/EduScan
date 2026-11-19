export function smsDeliveryLink({ status, message } = {}) {
  const params = new URLSearchParams({ tab: 'sms' });
  if (status) params.set('status', status);
  if (message) params.set('message', message);
  return '/dashboard/setup?' + params.toString() + '#sms-delivery';
}
