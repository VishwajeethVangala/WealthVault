import { useMemo } from 'react'
import { usePrivacy } from '../context/PrivacyContext'
import { compact, money, price, signedCompact, signedMoney } from './format'

const MASK = '₹ ••••'

/** Amount formatters that honour the "hide amounts" switch. Percentages and weights are never masked. */
export const useMoney = () => {
  const { hidden } = usePrivacy()
  return useMemo(() => {
    const guard =
      (fn: (v: number | null | undefined) => string) =>
      (v: number | null | undefined): string =>
        v == null ? fn(v) : hidden ? MASK : fn(v)
    return {
      hidden,
      money: guard((v) => money(v)),
      price: guard(price),
      compact: guard(compact),
      signedMoney: guard((v) => signedMoney(v)),
      signedCompact: guard(signedCompact),
    }
  }, [hidden])
}
