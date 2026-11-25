import { useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { api } from './merchantApi'
import { TryFitMirror, TryFitSample } from './TryFitMirror'

type Job = {
  job_id: string
  status: 'waiting' | 'processing' | 'done' | 'failed'
  error_message: string | null
}

type SelectedImage = { file: File; previewUrl: string }

type UploadFieldProps = {
  id: string
  title: string
  image: SelectedImage | null
  disabled: boolean
  onFile: (image: SelectedImage) => void
}

function UploadField({ id, title, image, disabled, onFile }: UploadFieldProps) {
  const previewUrl = image?.previewUrl
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) onFile({ file, previewUrl: URL.createObjectURL(file) })
    event.target.value = ''
  }

  return (
    <div className="upload-card">
      <h3>{title}</h3>
      <label className="upload-area" htmlFor={id}>
        <input id={id} type="file" className="visually-hidden" accept="image/jpeg,image/png,.jpg,.jpeg,.png" disabled={disabled} aria-label={title} onChange={handleChange} />
        {image && previewUrl
          ? <img src={previewUrl} alt={title + ' preview'} />
          : <span className="upload-symbol" aria-hidden="true">↑</span>}
        <span className="upload-action">{image ? 'Change photo' : 'Choose a photo'}</span>
      </label>
      <p className="upload-caption" title={image?.file.name}>{image ? image.file.name : 'JPG or PNG · up to 10 MB'}</p>
    </div>
  )
}

async function responseError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    return typeof body.detail === 'string' ? body.detail : 'The request could not be completed.'
  } catch {
    return 'Could not reach the try-on service.'
  }
}

export default function TryOnForm({ workspaceId, onJobChange }: { workspaceId: string; onJobChange?: () => void }) {
  const [person, setPerson] = useState<SelectedImage | null>(null)
  const [garment, setGarment] = useState<SelectedImage | null>(null)
  const [consent, setConsent] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [resultImage, setResultImage] = useState<{ jobId: string; url: string; originalUrl?: string } | null>(null)
  const [submittedPerson, setSubmittedPerson] = useState<{ jobId: string; file: File } | null>(null)
  const [modelAvailable, setModelAvailable] = useState<boolean | null>(null)
  const jobId = job?.job_id
  const activeJob = job?.status === 'waiting' || job?.status === 'processing'

  useEffect(() => {
    const request = new AbortController()
    api<{ model_available: boolean }>('/api/health', { signal: request.signal })
      .then(health => { if (!request.signal.aborted) setModelAvailable(health.model_available) })
      .catch(() => {})
    return () => request.abort()
  }, [])

  useEffect(() => {
    if (!jobId || !activeJob) return
    const request = new AbortController()
    let timer: number | undefined

    const poll = async () => {
      try {
        const response = await fetch('/api/jobs/' + encodeURIComponent(jobId), { cache: 'no-store', signal: request.signal, headers: { 'X-Organization-Id': workspaceId } })
        if (!response.ok) throw new Error(await responseError(response))
        const next: Job = await response.json()
        if (request.signal.aborted) return
        setError('')
        setJob(next)
        if (next.status === 'waiting' || next.status === 'processing') {
          timer = window.setTimeout(() => { void poll() }, 1200)
        } else {
          onJobChange?.()
        }
      } catch (cause) {
        if (!request.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not read job status.')
      }
    }

    void poll()
    return () => {
      request.abort()
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [jobId, activeJob, workspaceId, onJobChange])

  useEffect(() => {
    if (job?.status !== 'done') return
    const request = new AbortController()
    let url: string | undefined
    let originalUrl: string | undefined
    const loadImage = async () => {
      try {
        const response = await fetch('/api/jobs/' + encodeURIComponent(job.job_id) + '/result', {
          cache: 'no-store', signal: request.signal, headers: { 'X-Organization-Id': workspaceId },
        })
        if (!response.ok) throw new Error(await responseError(response))
        const blob = await response.blob()
        if (request.signal.aborted) return
        url = URL.createObjectURL(blob)
        if (submittedPerson?.jobId === job.job_id) originalUrl = URL.createObjectURL(submittedPerson.file)
        setResultImage({ url, originalUrl, jobId: job.job_id })
      } catch (cause) {
        if (!request.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load the preview.')
      }
    }
    void loadImage()
    return () => {
      request.abort()
      if (url) URL.revokeObjectURL(url)
      if (originalUrl) URL.revokeObjectURL(originalUrl)
    }
  }, [job, workspaceId, submittedPerson])

  async function removeJob() {
    if (!jobId) return

    const response = await fetch('/api/jobs/' + encodeURIComponent(jobId), { method: 'DELETE', headers: { 'X-Organization-Id': workspaceId } })
    if (!response.ok && response.status !== 404) throw new Error(await responseError(response))
    setJob(null)
    setSubmittedPerson(null)
    onJobChange?.()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!person || !garment || !consent || busy || (activeJob && !error)) return

    setBusy(true)
    setError('')
    try {
      await removeJob()
      const form = new FormData()
      form.set('consent', 'true')
      form.set('category', 'upper')
      form.set('person_image', person.file)
      form.set('garment_image', garment.file)
      const response = await fetch('/api/jobs', { method: 'POST', body: form, headers: { 'X-Organization-Id': workspaceId } })
      if (!response.ok) throw new Error(await responseError(response))
      const created: { job_id: string; status: Job['status'] } = await response.json()
      setSubmittedPerson({ jobId: created.job_id, file: person.file })
      setJob({ job_id: created.job_id, status: created.status, error_message: null })
      onJobChange?.()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start the try-on request.')
    } finally {
      setBusy(false)
    }
  }

  async function deleteImages() {
    setBusy(true)
    setError('')
    try {
      await removeJob()
      setPerson(null)
      setGarment(null)
      setConsent(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete the job.')
    } finally {
      setBusy(false)
    }
  }

  const waiting = busy || (activeJob && !error)
  const result = job?.status === 'done' && resultImage?.jobId === job.job_id ? resultImage : null
  const message = error || job?.error_message
  const status = job?.status === 'waiting' ? 'Your request is in the queue.'
    : job?.status === 'processing' ? 'Preparing your preview…'
      : job?.status === 'done' ? (result ? 'AI-generated preview ready.' : 'Loading your preview…')
        : 'Try-on generation failed.'

  return (
    <section className="studio" id="try-on" aria-labelledby="try-on-title">
      <div className="site-width">
        <div className="studio-heading">
          <h2 id="try-on-title">The fitting room</h2>
          <p>Upload your photo and a separate image of an upper-body garment.</p>
        </div>
        {modelAvailable === false && <p className="runtime-note" role="status">Live previews are currently unavailable on this server. Open the sample below to see the TryFit Mirror.</p>}
        <TryFitSample />
        <div className="studio-grid">
          <form className="studio-form" onSubmit={submit}>
            <div className="upload-grid">
              <UploadField id="person-image" title="Your photo" image={person} disabled={waiting} onFile={setPerson} />
              <UploadField id="garment-image" title="Garment image" image={garment} disabled={waiting} onFile={setGarment} />
            </div>
            <label className="consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              <span>I have permission to use these images and consent to temporary processing. Images are excluded from model training.</span>
            </label>
            <div className="studio-actions">
              <button className="button button-primary" type="submit" disabled={!person || !garment || !consent || waiting}>
                {waiting ? 'Working…' : 'Create preview'} <span aria-hidden="true">↗</span>
              </button>
              {(job || person || garment) && <button className="text-link delete-button" type="button" onClick={deleteImages} disabled={busy}>Delete images &amp; reset</button>}
            </div>
          </form>
          <div className="result-card">
            <div className="result-heading">
              <h3>{result?.originalUrl ? 'The TryFit Mirror' : 'Your preview'}</h3>
              {result && <span>AI-generated</span>}
            </div>
            <div className="result-stage" aria-live="polite">
              {result && !error
                ? result.originalUrl
                  ? <TryFitMirror key={jobId} original={result.originalUrl} result={result.url} />
                  : <img src={result.url} alt="AI-generated virtual try-on preview" />
                : <div className="result-message">
                    <span className="result-symbol" aria-hidden="true">{message ? '!' : '✧'}</span>
                    <strong>{error ? 'Request issue' : job ? status : 'Your result appears here'}</strong>
                    {message && <p>{message}</p>}
                  </div>}
            </div>
            <p className="result-note">AI-generated previews approximate appearance. Check the retailer’s size chart for fit.</p>
          </div>
        </div>
      </div>
    </section>
  )
}
