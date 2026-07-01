"use client";

import { useState } from "react";

export default function GovBanner() {
  const [open, setOpen] = useState(false);
  return (
    <section className="usa-banner" aria-label="Official government website">
      <div className="usa-accordion">
        <header className="usa-banner__header">
          <div className="usa-banner__inner">
            <div className="grid-col-auto">
              <img
                className="usa-banner__header-flag"
                src="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.1/dist/img/us_flag_small.png"
                alt="U.S. flag"
              />
            </div>
            <div className="grid-col-fill tablet:grid-col-auto" aria-hidden="true">
              <p className="usa-banner__header-text">
                An official website of the United States government
              </p>
              <p className="usa-banner__header-action">Here&rsquo;s how you know</p>
            </div>
            <button
              type="button"
              className="usa-accordion__button usa-banner__button"
              aria-expanded={open}
              aria-controls="gov-banner-content"
              onClick={() => setOpen((v) => !v)}
            >
              <span className="usa-banner__button-text">Here&rsquo;s how you know</span>
            </button>
          </div>
        </header>
        <div
          className="usa-banner__content usa-accordion__content"
          id="gov-banner-content"
          hidden={!open}
        >
          <div className="grid-row grid-gap-lg">
            <div className="usa-banner__guidance tablet:grid-col-6">
              <img
                className="usa-banner__icon usa-media-block__img"
                src="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.1/dist/img/icon-dot-gov.svg"
                role="img"
                alt=""
                aria-hidden="true"
              />
              <div className="usa-media-block__body">
                <p>
                  <strong>Official websites use .gov</strong>
                  <br />A <strong>.gov</strong> website belongs to an official government
                  organization in the United States.
                </p>
              </div>
            </div>
            <div className="usa-banner__guidance tablet:grid-col-6">
              <img
                className="usa-banner__icon usa-media-block__img"
                src="https://cdn.jsdelivr.net/npm/@uswds/uswds@3.8.1/dist/img/icon-https.svg"
                role="img"
                alt=""
                aria-hidden="true"
              />
              <div className="usa-media-block__body">
                <p>
                  <strong>Secure .gov websites use HTTPS</strong>
                  <br />A <strong>lock</strong> or <strong>https://</strong> means you&rsquo;ve
                  safely connected to the .gov website.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
