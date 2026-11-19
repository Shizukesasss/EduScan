import { useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import ActionMenu from '../Common/ActionMenu';
import Modal from '../Common/Modal';
import VerifyReport from './VerifyReport';

export default function SavedReportActions({ report, onPreview, onDownload, canDownload = true, disabled = false, table = false }) {
  const [verifying, setVerifying] = useState(false);
  const [working, setWorking] = useState(false);
  const { showError } = useToast();
  const path = `/reports/history/${encodeURIComponent(report.id)}/download`;
  const pdf = report.filename.toLowerCase().endsWith('.pdf');
  const run = async action => {
    setWorking(true);
    try { await action(); }
    catch (err) { showError(err.message); }
    finally { setWorking(false); }
  };
  const preview = onPreview || (canDownload && pdf ? () => api.openDocument(path) : null);
  if (!preview && !canDownload) return null;
  return <div className="saved-report-actions">
    <ActionMenu label="Report actions" disabled={disabled || working} table={table}>
      {preview && <button type="button" onClick={() => run(preview)}>Preview</button>}
      {canDownload && <button type="button" onClick={() => run(onDownload || (() => api.download(path, report.filename)))}>Download</button>}
    </ActionMenu>
    {canDownload && pdf && <button type="button" className="btn-link" disabled={disabled || working}
      onClick={() => setVerifying(true)}>Verify PDF</button>}
    {verifying && <Modal onClose={() => setVerifying(false)} label="Verify PDF">
      <div className="modal-card">
        <div className="modal-header"><h2>Verify PDF</h2></div>
        <VerifyReport report={report} />
        <div className="modal-actions"><button type="button" className="btn-secondary" onClick={() => setVerifying(false)}>Close</button></div>
      </div>
    </Modal>}
  </div>;
}
