
import './App.css';

function App() {
  return (
    <div className="website">

      {/* Navigation */}
      <nav className="navbar">
        <a href="#home" className="logo">
          TryFit<span> BD</span>
        </a>

        <div className="nav-links">
          <a href="#home">Home</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#about">About</a>
        </div>

        <a href="#how-it-works" className="nav-button">
          Try It On
        </a>
      </nav>

      {/* Hero */}
      <main>
        <section className="hero" id="home">

          <div className="hero-content">
            <span className="eyebrow">
              THE FUTURE OF ONLINE FASHION
            </span>

            <h1>
              Try Before <br />
              You <span>Buy.</span>
            </h1>

            <p>
              Discover how your favourite outfits may look on you.
              Experience AI-powered virtual clothing try-on
              designed for online shoppers in Bangladesh.
            </p>

            <a href="#how-it-works" className="primary-button">
              Start Virtual Try-On →
            </a>

            <div className="hero-note">
              Simple. Smart. More confident shopping.
            </div>
          </div>

          <div className="hero-visual">
            <div className="visual-card">
              <div className="visual-label">YOUR STYLE, YOUR WAY</div>
              <div className="visual-icon">✦</div>
              <div className="visual-title">
                A better way <br /> to try fashion.
              </div>
              <div className="visual-description">
                Preview your selected outfit with AI.
              </div>
              <div className="visual-bottom">
                <span>TRYFIT BD</span>
                <span>01 / 01</span>
              </div>
            </div>
          </div>

        </section>

        {/* How It Works */}
        <section className="how-section" id="how-it-works">
          <span className="eyebrow">THREE SIMPLE STEPS</span>
          <h2>How TryFit BD Works</h2>
          <p className="section-description">
            Explore your outfit before making a purchase.
          </p>

          <div className="steps">
            <article className="step-card">
              <span className="step-number">01</span>
              <h3>Upload Your Photo</h3>
              <p>Choose a suitable photo of yourself.</p>
            </article>

            <article className="step-card">
              <span className="step-number">02</span>
              <h3>Select Your Outfit</h3>
              <p>Choose a garment from the catalogue.</p>
            </article>

            <article className="step-card">
              <span className="step-number">03</span>
              <h3>Preview Your Look</h3>
              <p>See an AI-generated clothing preview.</p>
            </article>
          </div>
        </section>

        {/* About */}
        <section className="about-section" id="about">
          <span className="eyebrow">ABOUT THE PROJECT</span>
          <h2>Making online fashion shopping easier.</h2>
          <p>
            TryFit BD is a virtual clothing try-on project
            designed to help shoppers in Bangladesh preview
            selected garments using their own photos.
          </p>
        </section>
      </main>

      {/* Footer */}
      <footer className="footer">
        <a href="#home" className="logo">
          TryFit<span> BD</span>
        </a>
        <p>© 2026 TryFit BD. All rights reserved.</p>
      </footer>

    </div>
  );
}

export default App;
