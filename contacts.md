---
layout: page
title: Contacts
permalink: /contacts/
---

Some information about you!

... which is shown in the screenshot below:

![_config.yml]({{ site.baseurl }}/images/config.png)

<ul>
  {% for post in site.posts limit: 1 %}
    <li>
      <a href="{{site.baseurl}}{{ post.url }}">{{ post.title }}</a>
      {{ post.description }}
    </li>
  {% endfor %}
</ul>


### More Information

A place to include any other types of information that you'd like to include about yourself.

### Contact me


[email@domain.com](mailto:email@domain.com)
