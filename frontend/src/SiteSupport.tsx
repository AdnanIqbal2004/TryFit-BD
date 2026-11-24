import './SiteSupport.css'

const channels = [
  { name: 'Email', icon: 'M3 5h18v14H3z M3 6l9 7 9-7' },
  { name: 'Phone', icon: 'M7 3H4a1 1 0 0 0-1 1c0 9.4 7.6 17 17 17a1 1 0 0 0 1-1v-3l-5-2-2 2a14 14 0 0 1-7-7l2-2-2-5z' },
  { name: 'WhatsApp', icon: 'M5 18l-1 3 3-1a8.5 8.5 0 1 0-2-2z M9 8c-1 1 0 3 2 5s4 3 5 2l1-1-3-1-1 1a7 7 0 0 1-3-3l1-1-1-3z' },
]

const questions = [
  { title: 'What photos work best?', answer: 'Use a well-lit, front-facing photo with your upper body visible. Choose a separate, clear photo of a shirt, top, or cardigan. Both files should be JPG or PNG, up to 10 MB each.' },
  { title: 'Can the preview tell me my size?', answer: 'The preview is an AI-generated approximation of appearance. Use the retailer’s size chart to choose a size.' },
  { title: 'Can I remove my uploaded photos?', answer: 'Yes. Use Delete images & reset in the fitting room to remove the temporary images for that job.' },
]

export default function SiteSupport() {
  return (
    <section className="site-support" id="contact" aria-labelledby="contact-title">
      <div className="site-width support-grid">
        <div className="contact-preview">
          <h2 id="contact-title">Contact us</h2>
          <ul className="contact-icons" aria-label="Support channels">
            {channels.map(channel => (
              <li key={channel.name}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" focusable="false" aria-hidden="true"><path d={channel.icon} /></svg>
                <span className="visually-hidden">{channel.name}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="support-faq" aria-labelledby="faq-title">
          <h3 id="faq-title">Frequently asked questions</h3>
          {questions.map(question => (
            <details key={question.title}>
              <summary>{question.title}</summary>
              <p>{question.answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
