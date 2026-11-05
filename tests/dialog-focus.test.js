import test from 'node:test';
import assert from 'node:assert/strict';
import { trapDialogTab } from '../src/services/dialogFocus.js';
function fixture() {
 const doc = { activeElement: null };
 const control = (extra = {}) => ({ disabled: false, tabIndex: 0, closest: () => null, getClientRects: () => [1], focus() { doc.activeElement = this; }, ...extra });
 const first=control(), hidden=control({getClientRects:()=>[]}), disabled=control({disabled:true}), last=control();
 const dialog={ownerDocument:doc,querySelectorAll:()=>[first,hidden,disabled,last],focus(){doc.activeElement=this}};
 const event=(shiftKey=false)=>({key:'Tab',shiftKey,preventDefault(){this.prevented=true}});
 return {doc,first,last,dialog,event};
}
test('Tab wraps from last enabled visible control to first',()=>{const f=fixture();f.last.focus();const e=f.event();trapDialogTab(e,f.dialog);assert.equal(f.doc.activeElement,f.first);assert.equal(e.prevented,true)});
test('Shift+Tab wraps from first to last, ignoring hidden and disabled inputs',()=>{const f=fixture();f.first.focus();const e=f.event(true);trapDialogTab(e,f.dialog);assert.equal(f.doc.activeElement,f.last)});
test('Tab enters controls from the initially focused dialog',()=>{const f=fixture();f.dialog.focus();trapDialogTab(f.event(),f.dialog);assert.equal(f.doc.activeElement,f.first)});
test('empty dialog keeps focus and prevents escape by Tab',()=>{const f=fixture();f.dialog.querySelectorAll=()=>[];const e=f.event();trapDialogTab(e,f.dialog);assert.equal(f.doc.activeElement,f.dialog);assert.equal(e.prevented,true)});
test('interior Tab and other keys retain native behavior',()=>{const f=fixture();f.first.focus();const e=f.event();trapDialogTab(e,f.dialog);assert.equal(e.prevented,undefined);trapDialogTab({key:'Enter'},f.dialog);assert.equal(f.doc.activeElement,f.first)});
