import SignOut from "@/components/SignOut";

export default function SiteHeader() {
  return (
    <header className="usa-header usa-header--basic">
      <div className="usa-nav-container">
        <div className="usa-navbar">
          <div className="usa-logo">
            <span className="usa-logo__text">
              <a href="/" title="FAR Assistant">
                Acquisition.gov
                <span className="far-logo-sub"> · FAR Assistant</span>
              </a>
            </span>
          </div>
        </div>
        <nav aria-label="Primary navigation" className="usa-nav">
          <ul className="usa-nav__primary usa-accordion">
            <li className="usa-nav__primary-item">
              <a className="usa-nav__link" href="/">
                <span>Ask the FAR</span>
              </a>
            </li>
            <li className="usa-nav__primary-item">
              <a className="usa-nav__link" href="/clauses">
                <span>Clause matrix</span>
              </a>
            </li>
            <li className="usa-nav__primary-item">
              <a className="usa-nav__link" href="/graph">
                <span>Graph</span>
              </a>
            </li>
            <li className="usa-nav__primary-item">
              <a
                className="usa-nav__link"
                href="https://www.acquisition.gov/browse/index/far"
                target="_blank"
                rel="noreferrer"
              >
                <span>Browse the FAR</span>
              </a>
            </li>
            <li className="usa-nav__primary-item">
              <SignOut />
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
