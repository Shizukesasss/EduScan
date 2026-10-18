export default function BiometricConsent({ checked, onChange }) {
  return <div className="full-field">
    <label className="checkbox-field"><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} /><span>I confirm that authorized biometric enrollment consent is documented and the enrollment terms have been explained.</span></label>
    <details><summary>Biometric enrollment terms</summary>
      <ul className="muted-small">
        <li>Face samples are used to identify this person for school attendance and prevent duplicate enrollment.</li>
        <li>Encrypted face samples and recognition data are stored by the school. Access is restricted to authorized staff.</li>
        <li>Staff must explain the school's privacy notice and document the applicable consent or authorization, including parent or guardian authorization when applicable, before capturing a face.</li>
        <li>Do not enroll someone else's face. This checkbox records staff confirmation; it does not replace the person's documented consent.</li>
        <li>Staff-assisted registration and attendance remain available without face enrollment. Ask authorized staff about removing face enrollment or correcting personal details.</li>
      </ul>
    </details>
  </div>;
}
