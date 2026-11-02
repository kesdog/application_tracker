// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import EmailReference from '../../src/EmailReference.vue'

enableAutoUnmount(afterEach)

it('opens distinct messages separately and labels search fallbacks honestly', () => {
  const wrapper = mount(EmailReference, { props: {
    reference: 'https://mail.google.com/mail/?authuser=owner%40example.com#all/abc123\nApplication subject\njavascript:alert(1)',
    context: 'Engineer at Example',
  } })
  const links = wrapper.findAll('a')
  expect(links.map(link => link.text())).toEqual(['Open email 1', 'Find email 2'])
  expect(links[0].attributes('aria-label')).toBe('Open email 1 for Engineer at Example (opens in a new tab)')
  expect(links.every(link => link.attributes('target') === '_blank' && link.attributes('rel') === 'noopener noreferrer')).toBe(true)
  expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
})

it('uses only the primary direct message in a compact list', () => {
  const wrapper = mount(EmailReference, { props: {
    reference: 'Application subject\nhttps://mail.google.com/mail/?authuser=owner%40example.com#all/abc123\nhttps://mail.google.com/mail/?authuser=owner%40example.com#all/def456',
    primary: true,
  } })
  expect(wrapper.findAll('a')).toHaveLength(1)
  expect(wrapper.get('a').text()).toBe('Open email')
  expect(wrapper.get('a').attributes('href')).toContain('#all/abc123')
})
