/** US extended session (pre-market to after-hours): 04:00-20:00 ET on weekdays. */
export const usSessionActive = (): boolean => {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const mins = et.getHours() * 60 + et.getMinutes()
  return et.getDay() >= 1 && et.getDay() <= 5 && mins >= 4 * 60 && mins <= 20 * 60
}

/** NSE session window used for polling cadence: Mon-Fri 09:15-15:30 IST. */
export const indiaSessionActive = (): boolean => {
  const ist = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  const mins = ist.getHours() * 60 + ist.getMinutes()
  return ist.getDay() >= 1 && ist.getDay() <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
}
