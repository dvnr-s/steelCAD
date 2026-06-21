import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Download, Pencil } from 'lucide-react'
import toast from 'react-hot-toast'
import { estimatesApi } from '../api/client'

function formatCurrency(n) {
  return `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}
function formatRupee(n) {
  return `₹${Number(n).toLocaleString('en-IN')}`
}

function LineRow({ item, indent }) {
  return (
    <tr>
      <td style={{ paddingLeft: indent ? 28 : 12 }}>{item.label}</td>
      <td style={{ color: 'var(--c-text-muted)', fontSize: '0.8125rem' }}>{item.description}</td>
      <td className="ta-right font-mono">{item.quantity}</td>
      <td className="ta-center text-xs text-muted">{item.unit}</td>
      <td className="ta-right font-mono">{formatCurrency(item.rate)}</td>
      <td className="ta-right font-mono">{formatCurrency(item.cost)}</td>
    </tr>
  )
}

export default function EstimatePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [estimate, setEstimate] = useState(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    estimatesApi.get(id)
      .then(({ data }) => setEstimate(data))
      .catch(() => { toast.error('Estimate not found'); navigate('/') })
      .finally(() => setLoading(false))
  }, [id])

  const handleDownloadPdf = async () => {
    setDownloading(true)
    try {
      const { data, headers } = await estimatesApi.downloadPdf(id)
      const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `SteelCAD_Estimate_v${estimate.version_number}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('PDF download failed')
    } finally {
      setDownloading(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center" style={{ height: '100vh' }}>
      <div className="spinner" style={{ width: 36, height: 36 }} />
    </div>
  )

  if (!estimate) return null

  const bd = estimate.breakdown

  return (
    <div className="dashboard-layout">
      <nav className="dashboard-nav">
        <div className="flex items-center gap-3">
          <button className="btn btn-ghost btn-sm btn-icon" onClick={() => navigate(-1)}>
            <ArrowLeft size={17} />
          </button>
          <div>
            <span style={{ fontWeight: 700 }}>Estimate</span>
            <span className="badge badge-brand" style={{ marginLeft: 8 }}>v{estimate.version_number}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Link to={`/designs/${estimate.design_id}`} className="btn btn-secondary btn-sm">
            <Pencil size={14} /> Edit Design
          </Link>
          <button className="btn btn-primary btn-sm" onClick={handleDownloadPdf} disabled={downloading}>
            {downloading ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Download size={14} />}
            Download PDF
          </button>
        </div>
      </nav>

      <main className="dashboard-main fade-in">
        {/* Structure table */}
        <h2 style={{ marginBottom: 16 }}>Itemized Breakdown</h2>

        <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 24 }}>
          <table className="breakdown-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Description</th>
                <th className="ta-right">Qty</th>
                <th className="ta-center">Unit</th>
                <th className="ta-right">Rate</th>
                <th className="ta-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {/* Frame */}
              <tr className="region-header">
                <td colSpan={6}>Structure</td>
              </tr>
              <LineRow item={bd.frame} />
              {bd.splits?.map((s, i) => <LineRow key={i} item={s} />)}

              {/* Regions */}
              {bd.regions?.map((r) => (
                <>
                  <tr className="region-header" key={r.region_id + '-header'}>
                    <td colSpan={5}>{r.region_label} — {r.region_type.toUpperCase()} ({r.dimensions})</td>
                    <td className="ta-right font-mono">{formatCurrency(r.subtotal)}</td>
                  </tr>
                  {r.pane_structure && <LineRow key="pane" item={r.pane_structure} indent />}
                  {r.infill && <LineRow key="infill" item={r.infill} indent />}
                  {r.beading && <LineRow key="beading" item={r.beading} indent />}
                  {r.grill && <LineRow key="grill" item={r.grill} indent />}
                  {r.hardware?.map((h, i) => <LineRow key={`hw${i}`} item={h} indent />)}
                </>
              ))}
            </tbody>
          </table>
        </div>

        {/* Totals */}
        <div className="estimate-totals">
          {[
            ['Subtotal', formatCurrency(bd.subtotal)],
            bd.discount_amount > 0 && [
              `Discount${bd.discount_type === 'PERCENTAGE' ? ` (${bd.discount_value}%)` : ' (Flat)'}`,
              `− ${formatCurrency(bd.discount_amount)}`,
            ],
            ['Taxable Amount', formatCurrency(bd.taxable)],
            ['GST (18%)', formatCurrency(bd.gst)],
          ].filter(Boolean).map(([label, value]) => (
            <div key={label} className="flex justify-between" style={{ padding: '10px 20px', borderBottom: '1px solid var(--c-border)' }}>
              <span style={{ fontWeight: 500 }}>{label}</span>
              <span className="font-mono">{value}</span>
            </div>
          ))}
          <div className="estimate-grand-total">
            <span>Grand Total</span>
            <span className="font-mono">{formatRupee(bd.grand_total)}</span>
          </div>
          <div className="flex justify-between" style={{ padding: '12px 20px', background: 'var(--c-surface-3)' }}>
            <span style={{ fontWeight: 600, color: 'var(--c-accent)' }}>
              Advance ({bd.advance_pct}%)
            </span>
            <span className="font-mono" style={{ fontWeight: 700, color: 'var(--c-accent)' }}>
              {formatRupee(bd.advance_amount)}
            </span>
          </div>
        </div>
      </main>
    </div>
  )
}
