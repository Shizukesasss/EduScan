export default function PhoneNumberField({ label, value, onChange }) {
  return <label><span className="field-label">{label}</span><input className="input-field" type="tel" inputMode="tel" autoComplete="tel" placeholder="e.g. 09171234567" pattern="(09|[+]639|639)[0-9]{9}" title="Enter 09171234567 or +639171234567, without spaces" value={value || ''} onChange={event => onChange(event.target.value)} /><span className="muted-small">Philippine mobile: 09 + 9 digits, or +639 + 9 digits. Optional; leave blank if unavailable.</span></label>;
}
