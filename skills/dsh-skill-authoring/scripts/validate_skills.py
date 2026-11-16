"""Read-only DSH skill YAML, local-link and byte-inventory checker (PyYAML).

Does not import skill scripts, invoke DSH, read credentials, or run commands.
Exit: 0 structurally valid, 1 violations, 2 dependency/usage/report errors.
"""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True


def scan(root, archived=(), python_templates=()):
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError('PyYAML is required; YAML was not validated') from exc

    class StrictLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        values={}
        for key_node,value_node in node.value:
            key=loader.construct_object(key_node,deep=deep)
            if key in values:
                raise ValueError('duplicate YAML key: '+str(key))
            values[key]=loader.construct_object(value_node,deep=deep)
        return values
    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    root=Path(root).resolve()
    errors=[];warnings=[];skills=[];files=[];known={};archived_entries=[]
    archived=set(archived)
    if any(not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',n) for n in archived):raise RuntimeError('invalid archived skill name')
    if not root.is_dir():raise RuntimeError('skills root is not a directory')
    template_paths=set()
    for declared in python_templates:
        relative=Path(declared)
        if relative.is_absolute() or relative.drive:raise RuntimeError('python template must be a relative path inside skills root')
        candidate=root/relative
        resolved=candidate.resolve()
        if not resolved.is_relative_to(root):raise RuntimeError('python template escapes skills root')
        if candidate.is_symlink() or not candidate.is_file() or candidate.suffix!='.py':raise RuntimeError('python template must name an existing regular .py file')
        try:template_source=candidate.read_bytes().decode('utf-8-sig')
        except UnicodeDecodeError as exc:raise RuntimeError('python template must be UTF-8') from exc
        if '{op}' not in template_source:raise RuntimeError('python template must contain the explicit {op} token')
        template_paths.add(resolved)
    entries=sorted(root.glob('*/SKILL.md'))
    if not entries:raise RuntimeError('no skill entries discovered; zero checked is not success')
    for entry in entries:
        try:
            raw=entry.read_bytes();text=raw.decode('utf-8-sig')
            match=re.match(r'\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)',text,re.S)
            if not match:
                if entry.parent.name in archived:
                    archived_entries.append({'name':entry.parent.name,'path':str(entry.relative_to(root)),'reason':'explicit caller-declared archived entry without frontmatter'})
                    continue
                raise ValueError('missing frontmatter boundaries')
            value=yaml.load(match.group(1),Loader=StrictLoader)
            if not isinstance(value,dict):raise ValueError('frontmatter must be mapping')
            name=value.get('name');description=value.get('description')
            if not isinstance(name,str) or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',name):raise ValueError('invalid name')
            if name in known:raise ValueError('duplicate skill identity '+name)
            known[name]=str(entry)
            if not isinstance(description,str) or not description.strip():raise ValueError('description must be nonempty string')
            if name!=entry.parent.name:errors.append({'path':str(entry),'reason':'directory/name mismatch'})
            for key in ('disableModelInvocation','modelInvocable','userInvocable'):
                if key in value:raise ValueError('rejected legacy invocation key '+key)
            for key in ('disable-model-invocation','user-invocable'):
                if key in value and not isinstance(value[key],bool):raise ValueError(key+' must be YAML boolean')
            if 'whenToUse' in value and not isinstance(value['whenToUse'],str):raise ValueError('whenToUse must be string')
            length=len(re.sub(r'\s+',' ',description).strip().encode('utf-16-le'))//2
            if length>500:warnings.append({'path':str(entry),'reason':'description exceeds current default catalog max500; check configured value','utf16':length})
            skills.append({'name':name,'path':str(entry.relative_to(root)),'description_utf16':length,'model_invocable':value.get('disable-model-invocation') is not True,'user_invocable':value.get('user-invocable') is not False})
        except Exception as exc:
            errors.append({'path':str(entry),'reason':type(exc).__name__+': '+str(exc)})
    seen_templates=set()
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:continue
        if path.is_symlink():
            warnings.append({'path':str(path),'reason':'symlink skipped'});continue
        raw=path.read_bytes()
        row={'path':str(path.relative_to(root)),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        if path.suffix=='.py':
            is_template=path.resolve() in template_paths
            if is_template:seen_templates.add(path.resolve())
            try:
                source=raw.decode('utf-8-sig')
                if is_template:source=source.replace('{op}','validation_op')
                ast.parse(source,filename=str(path))
                row['python_syntax']='TEMPLATE_RENDER_PARSE_PASS' if is_template else 'PASS'
                if is_template:row['python_validation']='Only literal {op} replaced by validation_op; AST parsed; not executed'
            except (SyntaxError,UnicodeDecodeError) as exc:
                row['python_syntax']='TEMPLATE_RENDER_PARSE_FAIL' if is_template else 'FAIL'
                errors.append({'path':str(path),'reason':('Python template rendered syntax: ' if is_template else 'Python syntax: ')+str(exc)})
        if path.suffix=='.md':
            text=raw.decode('utf-8-sig')
            # Markdown local destinations only; backticked names are navigation hints.
            for dest in re.findall(r'\]\(([^)]+)\)',text):
                dest=dest.strip().strip('<>')
                if re.match(r'^[a-z][a-z0-9+.-]*:',dest,re.I) or dest.startswith('#'):continue
                dest=dest.split('#',1)[0]
                if not dest or any(c in dest for c in ('<','>')):continue
                target=(path.parent/dest).resolve()
                if not target.is_relative_to(root):errors.append({'path':str(path),'reason':'local link escapes skills root: '+dest})
                elif not target.exists():errors.append({'path':str(path),'reason':'missing local link: '+dest})
        files.append(row)
    if seen_templates!=template_paths:raise RuntimeError('declared python template was excluded from file validation')
    return {'root':str(root),'skill_count':len(skills),'archived_count':len(archived_entries),'archived':archived_entries,'python_templates':[str(path.relative_to(root)) for path in sorted(template_paths)],'file_count':len(files),'errors':errors,'warnings':warnings,'skills':skills,'files':files}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--archived',action='append',default=[],metavar='NAME',help='explicitly allow this named entry to have no frontmatter; repeat as needed, still hash its files')
    parser.add_argument('--python-template',action='append',default=[],metavar='RELATIVE_PATH',help='explicit UTF-8 .py template inside root containing {op}; replace only that token with validation_op for AST parsing, never execute; repeat as needed')
    args=parser.parse_args()
    try:
        result=scan(args.root,args.archived,args.python_template)
        if args.report:
            destination=args.report.resolve()
            if destination.is_relative_to(args.root.resolve()):raise RuntimeError('report must be outside audited root')
            destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({k:result[k] for k in ('skill_count','file_count','errors','warnings')},ensure_ascii=True))
        sys.exit(1 if result['errors'] else 0)
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__+': '+str(exc)},ensure_ascii=True),file=sys.stderr)
        sys.exit(2)
