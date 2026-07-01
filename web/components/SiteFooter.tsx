export default function SiteFooter() {
  return (
    <footer className="usa-footer usa-footer--slim margin-top-6">
      <div className="usa-footer__secondary-section">
        <div className="grid-container">
          <div className="grid-row grid-gap">
            <div className="usa-footer__logo grid-row mobile-lg:grid-col-8">
              <div className="mobile-lg:grid-col-auto">
                <p className="usa-footer__logo-heading">Federal Acquisition Regulation Assistant</p>
              </div>
            </div>
            <div className="usa-footer__contact-links mobile-lg:grid-col-4">
              <p className="usa-footer__contact-heading text-base">
                AI-generated guidance. Verify against the official FAR.
              </p>
            </div>
          </div>
        </div>
      </div>
      <div className="usa-identifier">
        <section className="usa-identifier__section usa-identifier__section--masthead" aria-label="Agency identifier">
          <div className="usa-identifier__container">
            <div className="usa-identifier__identity" aria-label="Agency description">
              <p className="usa-identifier__identity-domain">acquisition.gov</p>
              <p className="usa-identifier__identity-disclaimer">
                A demonstration assistant over the Federal Acquisition Regulation, retrieved with Amazon
                Bedrock and grounded in the official FAR text.
              </p>
            </div>
          </div>
        </section>
      </div>
    </footer>
  );
}
