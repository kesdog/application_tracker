// @vitest-environment jsdom
import '../support/browser'
import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import PrimeVue from 'primevue/config'
import PageTabs from '../../src/components/shared/PageTabs.vue'

enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())

it('exposes named panels, supports keyboard activation and retains unsaved entries when switching', async () => {
  const Host = defineComponent({
    components: { PageTabs },
    setup: () => ({ draft: ref(''), tabs: [{ value: 'message', label: 'Message' }, { value: 'schedule', label: 'Schedule', count: 0 }] }),
    template: `<PageTabs label="Editor views" :tabs="tabs"><template #message><input v-model="draft" aria-label="Draft" /></template><template #schedule><button>Reschedule</button></template></PageTabs>`,
  })
  const wrapper = mount(Host, { attachTo: document.body, global: { plugins: [[PrimeVue, { unstyled: true }]] } })
  expect(wrapper.get('[role=tablist]').attributes('aria-label')).toBe('Editor views')
  const tabs = wrapper.findAll('[role=tab]')
  const panels = wrapper.findAll('[role=tabpanel]')
  expect(tabs[0]!.attributes('aria-controls')).toBe(panels[0]!.attributes('id'))
  expect(panels[0]!.attributes('aria-labelledby')).toBe(tabs[0]!.attributes('id'))
  expect(panels[0]!.isVisible()).toBe(true)
  expect(panels[1]!.isVisible()).toBe(false)
  await wrapper.get('input').setValue('Keep this unfinished message')
  await tabs[0]!.trigger('keydown', { code: 'ArrowRight' })
  expect(document.activeElement).toBe(tabs[1]!.element)
  await tabs[1]!.trigger('keydown', { code: 'Enter' })
  expect(tabs[1]!.attributes('aria-selected')).toBe('true')
  expect(panels[0]!.isVisible()).toBe(false)
  expect(panels[1]!.isVisible()).toBe(true)
  expect(tabs[1]!.text()).toContain('0')
  await tabs[0]!.trigger('click')
  expect(wrapper.get('input').element.value).toBe('Keep this unfinished message')
})
