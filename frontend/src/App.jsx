import { useState, useRef } from 'react'
import './App.css'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || ''

export default function App() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('idle') // idle | uploading | done | error
  const [error, setError] = useState('')
  const [csvUrl, setCsvUrl] = useState(null)
  const [csvFilename, setCsvFilename] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)

  const handleFile = (f) => {
    if (!f) return
    setFile(f)
    setCsvUrl(null)
    setCsvFilename('')
    setError('')
    setStatus('idle')
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const handleSubmit = async () => {
    if (!file) return
    setStatus('uploading')
    setError('')
    setCsvUrl(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${BACKEND_URL}/api/extract`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Server error: ${res.status}`)
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const disposition = res.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : 'requirements.csv'

      setCsvUrl(url)
      setCsvFilename(filename)
      setStatus('done')
    } catch (err) {
      setError(err.message || 'Unknown error')
      setStatus('error')
    }
  }

  const reset = () => {
    setFile(null)
    setCsvUrl(null)
    setCsvFilename('')
    setError('')
    setStatus('idle')
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="page">
      <div className="card">
        <div className="header">
          <div className="logo">RE</div>
          <div>
            <h1>Requirements Extractor</h1>
            <p className="subtitle">Upload a document and let AI extract the requirements for you</p>
          </div>
        </div>

        <div
          className={`drop-zone ${dragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".txt,.pdf,.docx,.doc,.md,.rtf"
            style={{ display: 'none' }}
            onChange={(e) => handleFile(e.target.files[0])}
          />
          {file ? (
            <div className="file-info">
              <span className="file-icon">📄</span>
              <span className="file-name">{file.name}</span>
              <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
            </div>
          ) : (
            <div className="drop-hint">
              <span className="upload-icon">⬆</span>
              <p>Drop your file here or <span className="link">browse</span></p>
              <p className="formats">Supported: TXT, PDF, DOCX, MD, RTF</p>
            </div>
          )}
        </div>

        <div className="actions">
          {file && status !== 'uploading' && (
            <button className="btn btn-secondary" onClick={reset}>
              Clear
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!file || status === 'uploading'}
          >
            {status === 'uploading' ? (
              <span className="spinner-row"><span className="spinner" />Extracting requirements...</span>
            ) : (
              'Extract Requirements'
            )}
          </button>
        </div>

        {status === 'error' && (
          <div className="alert alert-error">
            <strong>Error:</strong> {error}
          </div>
        )}

        {status === 'done' && csvUrl && (
          <div className="result">
            <div className="alert alert-success">
              Requirements extracted successfully!
            </div>
            <a className="btn btn-download" href={csvUrl} download={csvFilename}>
              Download {csvFilename}
            </a>
          </div>
        )}
      </div>

      <footer>
        Powered by Claude claude-opus-4-6 &mdash; Requirements Extractor
      </footer>
    </div>
  )
}
