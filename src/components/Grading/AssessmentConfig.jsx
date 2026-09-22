import { useState } from 'react';
import { AlertCircle, CheckCircle, ChevronDown, ChevronRight, Plus, Trash2, X } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';

export default function AssessmentConfig({ components, onSave, onClose, disabled = false }) {
  const [compList, setCompList] = useState(() =>
    components.map((c) => ({
      ...c,
      items: c.items ? [...c.items] : [],
    }))
  );
  const [confirmChanges, setConfirmChanges] = useState(false);
  const [expanded, setExpanded] = useState(() =>
    components.reduce((acc, c, idx) => ({ ...acc, [idx]: true }), {})
  );
  const { showError } = useToast();

  const totalWeight = compList.reduce((sum, c) => sum + (Number(c.weight) || 0), 0);
  const isWeightValid = Math.abs(totalWeight - 100.0) < 0.01;

  const toggleExpand = (idx) => {
    setExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const handleCompChange = (idx, field, value) => {
    setCompList((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const addComponent = () => {
    setCompList((prev) => [
      ...prev,
      {
        name: `Component ${prev.length + 1}`,
        component_type: 'Written Work',
        weight: 0,
        items: Array.from({ length: 5 }, (_, i) => ({
          label: `Activity ${i + 1}`,
          max_score: 20,
        })),
      },
    ]);
    setExpanded((prev) => ({ ...prev, [compList.length]: true }));
  };

  const removeComponent = (idx) => {
    if (compList.length <= 1) {
      showError('At least one component is required.');
      return;
    }
    setCompList((prev) => prev.filter((_, i) => i !== idx));
  };

  const addItem = (compIdx) => {
    setCompList((prev) => {
      const next = [...prev];
      const comp = next[compIdx];
      const items = comp.items || [];
      const count = items.length + 1;
      const defaultMax = comp.name.toLowerCase().includes('written') ? 20 : 50;
      next[compIdx] = {
        ...comp,
        items: [...items, { label: `${comp.name} ${count}`, max_score: defaultMax }],
      };
      return next;
    });
  };

  const handleItemChange = (compIdx, itemIdx, field, value) => {
    setCompList((prev) => {
      const next = [...prev];
      const items = [...next[compIdx].items];
      items[itemIdx] = { ...items[itemIdx], [field]: value };
      next[compIdx] = { ...next[compIdx], items };
      return next;
    });
  };

  const removeItem = (compIdx, itemIdx) => {
    setCompList((prev) => {
      const next = [...prev];
      const items = next[compIdx].items.filter((_, i) => i !== itemIdx);
      next[compIdx] = { ...next[compIdx], items };
      return next;
    });
  };

  const handleSave = () => {
    if (!isWeightValid) {
      showError(`Component weights must total exactly 100% (currently ${totalWeight.toFixed(1)}%).`);
      return;
    }
    for (const c of compList) {
      if (!c.name.trim()) {
        showError('All component names must be non-empty.');
        return;
      }
      if (!c.items || c.items.length === 0) {
        showError(`Component "${c.name}" must have at least one assessment item.`);
        return;
      }
      for (const item of c.items) {
        if (!item.label.trim()) {
          showError(`Assessment labels under "${c.name}" cannot be empty.`);
          return;
        }
        if (Number(item.max_score) <= 0) {
          showError(`Max score for "${item.label}" must be greater than 0.`);
          return;
        }
      }
    }
    if (!confirmChanges) {
      showError('Please confirm the component changes for the audit trail.');
      return;
    }
    onSave(compList, 'Component structures and weights updated by teacher');
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card modal-lg">
        <div className="modal-header">
          <div>
            <h3>Configure Assessment Components</h3>
            <p className="modal-subtitle">
              Adjust assessment categories, percentage weights, and individual activities.
            </p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {/* Weight progress bar */}
          <div className="weight-progress-box">
            <div className="weight-progress-label">
              <span>Total Weight Allocation:</span>
              <strong className={isWeightValid ? 'text-success' : 'text-danger'}>
                {totalWeight.toFixed(1)}% / 100.0%
              </strong>
            </div>
            <div className="progress-bar-track">
              <div
                className={`progress-bar-fill ${isWeightValid ? 'bg-success' : totalWeight > 100 ? 'bg-danger' : 'bg-warning'}`}
                style={{ width: `${Math.min(100, totalWeight)}%` }}
              />
            </div>
            {!isWeightValid && (
              <p className="muted-small text-warning">
                {totalWeight < 100
                  ? `Need ${(100 - totalWeight).toFixed(1)}% more to reach 100%`
                  : `Exceeds 100% by ${(totalWeight - 100).toFixed(1)}%`}
              </p>
            )}
          </div>

          <div className="component-config-list">
            {compList.map((comp, cIdx) => (
              <div key={comp.id || cIdx} className="card-static comp-config-card">
                <div className="comp-config-header">
                  <button
                    type="button"
                    className="comp-accordion-btn"
                    onClick={() => toggleExpand(cIdx)}
                  >
                    {expanded[cIdx] ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    <span className="comp-title-badge">{comp.name || 'Untitled Component'}</span>
                    <span className="badge badge-subtle">{comp.weight}%</span>
                    <span className="badge-count">
                      {comp.items?.length || 0} item{comp.items?.length === 1 ? '' : 's'}
                    </span>
                  </button>
                  {!disabled && (
                    <button
                      type="button"
                      className="btn-text-danger"
                      onClick={() => removeComponent(cIdx)}
                      title="Delete this component"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>

                {expanded[cIdx] && (
                  <div className="comp-config-content">
                    <div className="form-grid three-columns">
                      <label>
                        <span className="field-label">Component Name</span>
                        <input
                          type="text"
                          className="input-field"
                          value={comp.name}
                          disabled={disabled}
                          onChange={(e) => handleCompChange(cIdx, 'name', e.target.value)}
                          placeholder="e.g. Written Work"
                        />
                      </label>
                      <label>
                        <span className="field-label">Type</span>
                        <select
                          className="input-field"
                          value={comp.component_type || 'Written Work'}
                          disabled={disabled}
                          onChange={(e) => handleCompChange(cIdx, 'component_type', e.target.value)}
                        >
                          <option value="Written Work">Written Work</option>
                          <option value="Performance Task">Performance Task</option>
                          <option value="Quarterly Assessment">Quarterly Assessment</option>
                        </select>
                      </label>
                      <label>
                        <span className="field-label">Weight (%)</span>
                        <input
                          type="number"
                          step="1"
                          min="0"
                          max="100"
                          className="input-field"
                          value={comp.weight}
                          disabled={disabled}
                          onChange={(e) => handleCompChange(cIdx, 'weight', Number(e.target.value))}
                        />
                      </label>
                    </div>

                    {/* Sub-items */}
                    <div className="items-config-section">
                      <div className="items-config-header">
                        <span className="section-label">Assessment Activities</span>
                        {!disabled && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => addItem(cIdx)}
                          >
                            <Plus size={14} /> Add Activity
                          </button>
                        )}
                      </div>

                      <div className="items-table-wrapper">
                        <table className="table table-compact items-table">
                          <thead>
                            <tr>
                              <th>Label</th>
                              <th style={{ width: '130px' }}>Max Score</th>
                              {!disabled && <th style={{ width: '48px' }}></th>}
                            </tr>
                          </thead>
                          <tbody>
                            {comp.items.map((item, iIdx) => (
                              <tr key={item.id || iIdx}>
                                <td>
                                  <input
                                    type="text"
                                    className="input-field-inline"
                                    value={item.label}
                                    disabled={disabled}
                                    onChange={(e) =>
                                      handleItemChange(cIdx, iIdx, 'label', e.target.value)
                                    }
                                    placeholder="Activity label"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="number"
                                    min="1"
                                    step="1"
                                    className="input-field-inline"
                                    value={item.max_score}
                                    disabled={disabled}
                                    onChange={(e) =>
                                      handleItemChange(
                                        cIdx,
                                        iIdx,
                                        'max_score',
                                        Number(e.target.value)
                                      )
                                    }
                                  />
                                </td>
                                {!disabled && (
                                  <td>
                                    <button
                                      type="button"
                                      className="btn-icon-danger"
                                      disabled={comp.items.length <= 1}
                                      onClick={() => removeItem(cIdx, iIdx)}
                                      title="Remove activity"
                                    >
                                      <Trash2 size={14} />
                                    </button>
                                  </td>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {!disabled && (
            <button type="button" className="btn btn-secondary add-comp-btn" onClick={addComponent}>
              <Plus size={16} /> Add Another Component
            </button>
          )}

          {!disabled && (
            <div className="change-reason-box" style={{ padding: '12px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', marginTop: '16px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', margin: 0 }}>
                <input
                  type="checkbox"
                  checked={confirmChanges}
                  onChange={(e) => setConfirmChanges(e.target.checked)}
                  style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                />
                <span className="field-label" style={{ margin: 0, fontWeight: 600, color: '#334155' }}>
                  I confirm these component changes are correct and authorize the audit trail log.
                </span>
              </label>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          {!disabled && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!isWeightValid || !confirmChanges}
              onClick={handleSave}
            >
              <CheckCircle size={16} /> Save Changes
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
