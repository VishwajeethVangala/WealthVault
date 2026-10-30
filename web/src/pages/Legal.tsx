import React, { useEffect, useState } from 'react'
import { fetchAuthConfig } from '../utils/api'

/** Public pages (no sign-in): the privacy policy and how to delete an account. Google Play asks for both as web links. */

const UPDATED = '16 October 2026'

export const DISCLAIMER =
  'WealthVault shows your own broker holdings and analysis built from public price history. It is information, not investment advice, and not a recommendation to buy or sell anything. Signals can be wrong; decide for yourself.'

const useSupportEmail = (): string => {
  const [email, setEmail] = useState('')
  useEffect(() => {
    fetchAuthConfig()
      .then((c) => setEmail(c.support_email ?? ''))
      .catch(() => undefined)
  }, [])
  return email
}

const Shell: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="legal">
    <article className="legal-card">
      <a className="legal-brand" href="/">
        <img src="/favicon.svg" alt="" width={28} height={28} />
        WealthVault
      </a>
      <h1>{title}</h1>
      <p className="legal-meta">Last updated {UPDATED}</p>
      {children}
      <p className="legal-foot">
        <a href="/privacy">Privacy policy</a> · <a href="/delete-account">Delete your account</a> · <a href="/">Open the app</a>
      </p>
    </article>
  </div>
)

const Contact: React.FC = () => {
  const email = useSupportEmail()
  return email ? <a href={`mailto:${email}`}>{email}</a> : <span>the contact email on the app&apos;s store listing</span>
}

export const PrivacyPolicy: React.FC = () => (
  <Shell title="Privacy policy">
    <p>
      WealthVault is a private portfolio tracker. It brings your holdings from your own broker accounts into one view and shows analysis of
      them. This page explains what it keeps, why, and how to remove it.
    </p>

    <h2>What we collect</h2>
    <ul>
      <li>
        <b>Your Google account details</b> when you sign in: name, email address, profile picture and Google account id. They identify your
        account.
      </li>
      <li>
        <b>Portfolio data from the brokers you connect</b> (for example Zerodha, INDmoney, Angel One): your holdings, quantities, prices and
        value, and the name of each connection. We also keep a daily record of your portfolio value so charts can show history.
      </li>
      <li>
        <b>Broker logins.</b> Where a broker needs an API key, it is stored encrypted. For Zerodha and INDmoney you log in on the broker&apos;s
        own page and we keep only the session it gives back, never your broker password.
      </li>
      <li>
        <b>Your settings</b>, such as target allocation.
      </li>
      <li>
        <b>Your phone&apos;s or browser&apos;s notification address</b> (a code Google&apos;s push service gives the Android app or the browser), only if you allow notifications,
        together with your notification choices. It is used to send you the alerts you picked and is removed when you sign out or delete your
        account. The alerts themselves are fetched from WealthVault when they arrive, so stock names and amounts do not pass through Google&apos;s
        push service, and the lock screen shows only a plain line.
      </li>
      <li>
        <b>Raw broker responses</b>, kept so figures can be checked and rebuilt if a broker changes its format.
      </li>
    </ul>

    <h2>What we do not do</h2>
    <ul>
      <li>We do not sell your data, and there is no advertising. The only data that leaves our storage is the optional usage data and crash reports described below, and only if you allow it.</li>
      <li>We cannot place trades or move money. The app only reads your holdings.</li>
      <li>The app does not read your contacts, location, photos or messages.</li>
    </ul>

    <h2>Usage data and crash reports (optional)</h2>
    <p>
      The first time you open the app, and again in <b>Account</b> (web) or <b>Settings</b> (Android), you are asked whether to share usage data.
      Nothing is sent unless you choose <b>Allow</b>, and you can switch it off at any time. If you allow it, we use Google Analytics and
      Firebase (Google) to learn which screens are used and what people search for, and to receive crash reports, so we can fix what is slow
      or missing.
    </p>
    <ul>
      <li>
        <b>What is sent:</b> which screen you opened, when you sign in, connect a broker, sync, refresh signals or run the strategy; the text you
        type into the stock search boxes on the Momentum and ATH Strategy pages (and the stock you pick); whether you turned on app lock; and
        technical details such as app version, device model and country. Crash reports include the error and the state of the app when it
        happened.
      </li>
      <li>
        <b>What is never sent:</b> your amounts, holdings, quantities, broker details, email address or name. Searches on the Holdings page are
        not recorded. Search text that looks like an email address or a long number is dropped.
      </li>
      <li>
        <b>Who you are:</b> events are tied to a random code made from your account id, not to your name or email. We do not use advertising
        features, Google signals or the Android advertising ID.
      </li>
      <li>
        <b>How long:</b> usage data is kept for 14 months and then removed automatically. To have your usage data removed sooner, email{' '}
        <Contact />.
      </li>
    </ul>

    <h2>Where it is stored and who else sees it</h2>
    <p>
      Your data is stored in Microsoft Azure storage and is separated per user, so no one else signed in can see it. The app talks to Google
      (sign-in) and to the brokers you choose to connect. It also reads public price and fund-value sources; those requests contain stock or
      fund names only, never anything about you.
    </p>

    <h2>On your device</h2>
    <p>
      The apps keep a sign-in token on your device so you stay signed in. The Android app does not save your portfolio data for offline
      use. The Android app requires the <b>app lock</b>: it asks for your phone&apos;s own fingerprint, face or screen lock each time you
      open it. That check is done by Android; WealthVault never receives or stores your fingerprint, face or PIN.
    </p>

    <h2>Keeping and deleting your data</h2>
    <p>
      We keep your data until you delete it. In the web app open <b>Account → Delete my account and data</b>; in the Android app open{' '}
      <b>More → Settings → Delete my account</b>. Either one erases everything listed above at once. You can also remove a single broker, with its holdings, from the Brokers page. More detail is on the{' '}
      <a href="/delete-account">delete your account</a> page. You can also email <Contact /> to ask for deletion.
    </p>

    <h2>Not financial advice</h2>
    <p>{DISCLAIMER}</p>

    <h2>Who can use it</h2>
    <p>WealthVault is for adults (18 and over).</p>

    <h2>Contact</h2>
    <p>
      Questions or requests: <Contact />.
    </p>
  </Shell>
)

export const DeleteAccountInfo: React.FC = () => (
  <Shell title="Delete your account">
    <p>You can delete your WealthVault account and everything stored with it at any time.</p>

    <h2>In the Android app</h2>
    <ol>
      <li>
        Open <b>More</b>, then <b>Settings</b>.
      </li>
      <li>
        Choose <b>Delete my account</b>.
      </li>
      <li>Type DELETE to confirm.</li>
    </ol>

    <h2>In the web app</h2>
    <ol>
      <li>
        Sign in and tap your profile picture at the top right to open <b>Account</b>.
      </li>
      <li>
        Choose <b>Delete my account and data</b>.
      </li>
      <li>Type DELETE to confirm.</li>
    </ol>

    <h2>What is erased</h2>
    <ul>
      <li>Your profile (name, email, picture)</li>
      <li>All holdings and daily portfolio history</li>
      <li>Your target allocation and settings</li>
      <li>Broker connections and the saved broker logins and API keys</li>
      <li>Raw broker responses kept for checking figures</li>
    </ul>
    <p>The deletion is immediate and cannot be undone. Public market prices shared by everyone are not personal data and are not removed.</p>

    <h2>Cannot sign in?</h2>
    <p>
      Email <Contact /> from the address you signed up with and ask for your account to be deleted.
    </p>

    <p>
      To stop a broker sharing data with WealthVault without deleting your account, use the <b>Brokers</b> page, or revoke access in that
      broker&apos;s own settings.
    </p>
  </Shell>
)
