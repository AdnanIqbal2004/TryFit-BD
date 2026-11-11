import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'

type Job = {
  job_id: string
  status: 'waiting' | 'processing' | 'done' | 'failed'
  error_message: string | null
}

type UploadFieldProps = {
  id: string
  title: string
  file: File | null
  onFile: (file: File | null) => void
}

function UploadField({ id, title, file, onFile }: UploadFieldProps) {
  const previewUrl = useMemo(() => file ? URL.createObjectURL(file) : '', [file])
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    onFile(event.target.files?.[0] ?? null)
    event.target.value = ''
  }

  return (
    <div className="try-on-upload">
      <label htmlFor={id}>{title}</label>
      <input key={file ? file.name : 'empty-' + id} id={id} type="file" accept="image/jpeg,image/png,.jpg,.jpeg,.png" onChange={handleChange} />
      {previewUrl && <img className="try-on-preview" src={previewUrl} alt={title + ' preview'} />}
      <span>{file ? file.name : 'JPG or PNG, up to 10 MB'}</span>
    </div>
  )
}

async function responseError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    return typeof body.detail === 'string' ? body.detail : 'The request could not be completed.'
  } catch {
    return 'Could not reach the backend. Make sure it is running on port 8000.'
  }
}

export default function TryOnForm() {
  const [person, setPerson] = useState<File | null>(null)
  const [garment, setGarment] = useState<File | null>(null)
  const [category, setCategory] = useState('upper')
  const [consent, setConsent] = useState(false)
  const [jobId, setJobId] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!jobId || job?.status === 'done' || job?.status === 'failed') return
    let active = true
    let timer: number | undefined
    const poll = async () => {
      try {
        const response = await fetch('/api/jobs/' + encodeURIComponent(jobId), { cache: 'no-store' })
        if (!response.ok) throw new Error(await responseError(response))
        const next: Job = await response.json()
        if (!active) return
        setJob(next)
        if (next.status === 'waiting' || next.status === 'processing') {
          timer = window.setTimeout(() => { void poll() }, 1200)
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not read job status.')
      }
    }
    void poll()
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [jobId, job?.status])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!person || !garment || !consent) return
    setBusy(true)
    setError('')
    const previousJobId = jobId
    setJobId('')
    setJob(null)
    try {
      if (previousJobId) {
        const removeResponse = await fetch('/api/jobs/' + encodeURIComponent(previousJobId), { method: 'DELETE' })
        if (!removeResponse.ok && removeResponse.status !== 404) {
          throw new Error(await responseError(removeResponse))
        }
      }
      const form = new FormData()
      form.set('consent', 'true')
      form.set('category', category)
      form.set('person_image', person)
      form.set('garment_image', garment)
      const response = await fetch('/api/jobs', { method: 'POST', body: form })
      if (!response.ok) throw new Error(await responseError(response))
      const created: { job_id: string; status: Job['status'] } = await response.json()
      setJobId(created.job_id)
      setJob({ job_id: created.job_id, status: created.status, error_message: null })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start the try-on request.')
    } finally {
      setBusy(false)
    }
  }

  async function deleteImages() {
    setError('')
    if (jobId) {
      try {
        const response = await fetch('/api/jobs/' + encodeURIComponent(jobId), { method: 'DELETE' })
        if (!response.ok && response.status !== 404) throw new Error(await responseError(response))
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Could not delete the job.')
        return
      }
    }
    setJobId('')
    setJob(null)
    setPerson(null)
    setGarment(null)
    setConsent(false)
  }

  const waiting = busy || job?.status === 'waiting' || job?.status === 'processing'
  const statusText = job?.status === 'waiting' ? 'Your request is in the queue…'
    : job?.status === 'processing' ? 'Preparing your preview…'
      : job?.status === 'done' ? 'Your preview is ready.'
        : job?.status === 'failed' ? 'Try-on generation failed.' : ''

  return (
    <section className="try-on-section" id="try-on" aria-labelledby="try-on-title">
      <span className="eyebrow">YOUR VIRTUAL FITTING ROOM</span>
      <h2 id="try-on-title">Build your try-on preview</h2>
      <p className="try-on-intro">Choose a person photo and a garment image to submit a private preview request. Generation is not active until a try-on model is approved and configured.</p>
      <form onSubmit={submit}>
        <div className="try-on-fields">
          <UploadField id="person-image" title="Your photo" file={person} onFile={setPerson} />
          <UploadField id="garment-image" title="Garment image" file={garment} onFile={setGarment} />
        </div>
        <div className="try-on-controls">
          <label className="try-on-category">Garment type
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="upper">Top / upper body</option>
              <option value="lower">Bottom / lower body</option>
              <option value="dress">Dress</option>
            </select>
          </label>
          <label className="try-on-consent">
            <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
            I have permission to use these images and consent to their temporary processing. They are not used to train a model.
          </label>
          <button className="primary-button" type="submit" disabled={!person || !garment || !consent || waiting}>
            {waiting ? 'Working…' : 'Create preview'}
          </button>
        </div>
      </form>
      {(job || error) && <div className="try-on-status" aria-live="polite">
        <strong>{error ? 'Request issue' : statusText}</strong>
        {(error || job?.error_message) && <p>{error || job?.error_message}</p>}
        {job?.status === 'done' && <img className="try-on-result" src={'/api/jobs/' + encodeURIComponent(job.job_id) + '/result'} alt="Generated virtual try-on preview" />}
      </div>}
      {(jobId || person || garment) && <button className="try-on-delete" type="button" onClick={deleteImages}>Delete temporary images and start over</button>}
      <p className="try-on-disclaimer">TryFit BD is an academic prototype. Results do not predict size, fit, color, fabric, or comfort.</p>
    </section>
  )
}



